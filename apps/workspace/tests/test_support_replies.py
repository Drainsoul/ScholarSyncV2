"""Replies to support requests, in the app or by email (spec §4.8, §9 rev 35)."""

from datetime import datetime
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import ProgramFactory
from apps.workspace import emails, support
from apps.workspace.models import EmailOutbox, Notification, SupportReply, SupportRequest
from apps.workspace.tests.factories import SupportReplyFactory, SupportRequestFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> Any:
    time_machine.move_to(NOW)
    return time_machine


@pytest.fixture
def office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, full_name="Jessica Tate")


def _request(**fields: Any) -> SupportRequest:
    sender = fields.pop("sender", None) or UserFactory.create(full_name="Ana Reyes")
    return SupportRequestFactory.create(sender=sender, **fields)


def _reply(actor: User, row: SupportRequest, body: str = "Two weeks.") -> SupportReply:
    return support.reply(actor=actor, request_row=row, body=body, template=None, now=NOW)


def _email(actor: User, row: SupportRequest, body: str = "Two weeks.") -> SupportReply:
    return support.email_reply(
        actor=actor,
        request_row=row,
        subject="Re: your message about an application",
        body=body,
        template=None,
        now=NOW,
    )


def test_first_reply_answers_and_records_both_events(office: User) -> None:
    row = _request()
    reply = _reply(office, row, body="Secret answer text")
    row.refresh_from_db()
    assert (row.status, row.answered_by, row.answered_at) == (
        SupportRequest.Status.ANSWERED,
        office,
        NOW,
    )
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"support.answered", "support.replied"} <= actions
    event = AuditEvent.objects.get(action="support.replied")
    assert event.data == {
        "request": row.pk,
        "reply": reply.pk,
        "channel": "app",
        "template": None,
        "program": None,
    }
    assert not any("Secret" in str(e.data) for e in AuditEvent.objects.all())


def test_later_reply_keeps_first_answerer(office: User, _frozen: Any) -> None:
    row = _request()
    _reply(office, row)
    other = UserFactory.create(role=User.Role.SUPER_ADMIN)
    _frozen.shift(3600)
    support.reply(actor=other, request_row=row, body="More.", template=None, now=timezone.now())
    row.refresh_from_db()
    assert (row.answered_by, row.answered_at) == (office, NOW)
    assert row.replies.count() == 2
    assert AuditEvent.objects.filter(action="support.answered").count() == 1


def test_app_reply_notifies_without_email(office: User) -> None:
    row = _request()
    _reply(office, row)
    note = Notification.objects.get()
    assert (note.recipient, note.kind, note.title, note.body, note.url) == (
        row.sender,
        "support_replied",
        "The scholarship office answered your message",
        "",
        "/me/support/replies/",
    )
    assert not EmailOutbox.objects.exists()


def test_program_staff_reply_signs_with_program() -> None:
    program = ProgramFactory.create(name="LANI")
    staff = UserFactory.create(role=User.Role.STAFF)
    row = _request(program=program)
    _reply(staff, row)
    assert Notification.objects.get().title == "LANI answered your message"


def test_email_reply_queues_support_reply(office: User) -> None:
    row = _request()
    reply = _email(office, row)
    outbox = EmailOutbox.objects.get()
    assert (outbox.to, outbox.kind) == (row.sender.email, "support_reply")
    assert set(outbox.context) == {"full_name", "subject", "body", "replies_url"}
    assert reply.email == outbox
    assert reply.channel == "email"
    assert Notification.objects.get().kind == "support_replied"


def test_email_html_escapes_and_keeps_lines(office: User) -> None:
    row = _request()
    _email(office, row, body="<script>alert(1)</script>\nline two")
    subject, text, html = emails._render(EmailOutbox.objects.get())
    assert subject == "Re: your message about an application"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;<br>line two" in html
    assert "<script>alert(1)</script>\nline two" in text
    footer = (
        "This address doesn't take replies. "
        "To ask something else, sign in and open Help and guides."
    )
    assert footer in text
    assert footer in html
    assert "Jessica Tate" not in text and "Jessica Tate" not in html


def test_email_greets_there_without_a_name(office: User) -> None:
    row = _request(sender=UserFactory.create(full_name=""))
    _email(office, row)
    _, text, _ = emails._render(EmailOutbox.objects.get())
    assert "Hi there," in text


def test_duplicate_within_60_seconds_refused(office: User, _frozen: Any) -> None:
    row = _request()
    _reply(office, row)
    with pytest.raises(ValidationError) as caught:
        _reply(office, row)
    assert caught.value.messages == [support.DUPLICATE_MESSAGE]
    assert support.DUPLICATE_MESSAGE == "This reply was already sent."
    _frozen.shift(61)
    support.reply(
        actor=office, request_row=row, body="Two weeks.", template=None, now=timezone.now()
    )
    assert row.replies.count() == 2


def test_email_refused_for_inactive_account(office: User) -> None:
    row = _request(sender=UserFactory.create(is_active=False))
    with pytest.raises(ValidationError) as caught:
        _email(office, row)
    assert caught.value.messages == ["This student's account is closed. Reply in the app instead."]
    assert not EmailOutbox.objects.exists()
    assert _reply(office, row).pk


def test_scoped_request_404s_outside_program() -> None:
    mine, theirs = ProgramFactory.create(), ProgramFactory.create()
    own = _request(program=mine)
    other = _request(program=theirs)
    loose = _request()
    assert support.scoped_request(mine, own.pk) == own
    for row in (other, loose):
        with pytest.raises(Http404):
            support.scoped_request(mine, row.pk)
    assert support.scoped_request(None, other.pk) == other
    assert support.scoped_request(None, loose.pk) == loose


def test_inbox_rows_scope_and_reply_count() -> None:
    mine = ProgramFactory.create()
    own = _request(program=mine)
    _request()
    SupportReplyFactory.create_batch(2, request=own)
    rows = list(support.inbox_rows(mine, "open"))
    assert rows == [own]
    assert rows[0].reply_count == 2  # type: ignore[attr-defined]
    assert len(support.inbox_rows(None, "open")) == 2
    assert support.open_count(mine) == 1
    assert support.open_count() == 2


def test_unread_and_mark_read_are_per_student(office: User) -> None:
    mine = _request()
    theirs = _request()
    _reply(office, mine)
    _reply(office, theirs, body="Other")
    assert support.unread_replies(mine.sender) == 1
    assert [r.request for r in support.student_replies(mine.sender)] == [mine]
    assert support.mark_replies_read(mine.sender, NOW) == 1
    assert support.unread_replies(mine.sender) == 0
    assert support.unread_replies(theirs.sender) == 1


def test_new_send_copy() -> None:
    assert support.LIMIT_MESSAGE == "You've sent 5 messages today. Try again tomorrow."
    assert support.SEND_SUCCESS == "Message sent. You'll find the answer under Replies."
