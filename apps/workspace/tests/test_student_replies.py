"""The student's Replies tab under Help and guides (spec §12 rev 35)."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import EmailOutbox, SupportReply
from apps.workspace.tests.factories import SupportReplyFactory, SupportRequestFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=TZ)
FORM = "/me/support/"
REPLIES = "/me/support/replies/"


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> Any:
    time_machine.move_to(NOW)
    return time_machine


@pytest.fixture
def student(client: Any) -> User:
    user = UserFactory.create(full_name="Ana Reyes")
    client.force_login(user)
    return user


def _staff(name: str = "Maria Santos") -> User:
    return UserFactory.create(role=User.Role.STAFF, full_name=name)


def test_tabs_with_unread_count_on_both_pages(client: Any, student: User) -> None:
    SupportReplyFactory.create(request=SupportRequestFactory.create(sender=student))
    for url in (FORM, REPLIES):
        response = client.get(url)
        tabs = {tab["label"]: tab for tab in response.context["tabs"]}
        assert list(tabs) == ["Contact the office", "Replies"]
        assert tabs["Replies"]["count"] == 1


def test_messages_show_reply_count_link(client: Any, student: User) -> None:
    row = SupportRequestFactory.create(sender=student)
    SupportReplyFactory.create(request=row)
    html = client.get(FORM).content.decode()
    assert f'<a href="{REPLIES}">1 reply</a>' in html


def test_replies_listed_newest_first_with_question_and_sender(client: Any, student: User) -> None:
    lani = ProgramFactory.create(name="LANI")
    long_question = "Q" * 250
    first = SupportRequestFactory.create(sender=student, topic="allowance", message=long_question)
    second = SupportRequestFactory.create(sender=student, program=lani, topic="application")
    SupportReplyFactory.create(request=first, body="Office answer")
    SupportReply.objects.update(created_at=NOW - timedelta(hours=1))
    outbox = EmailOutbox.objects.create(to=student.email, kind="support_reply")
    SupportReplyFactory.create(
        request=second,
        author=_staff(),
        channel="email",
        subject="Re: your message",
        body="Program answer",
        email=outbox,
    )
    html = client.get(REPLIES).content.decode()
    assert html.index("Program answer") < html.index("Office answer")
    assert "From LANI" in html and "From The scholarship office" in html
    assert "Sent by email" in html
    assert "Q" * 200 + "…" in html and "Q" * 201 not in html
    assert "An allowance" in html and "An application" in html
    assert "Maria Santos" not in html


def test_new_marks_then_read(client: Any, student: User) -> None:
    SupportReplyFactory.create(request=SupportRequestFactory.create(sender=student))
    assert ">New<" in client.get(REPLIES).content.decode()
    second = client.get(REPLIES)
    assert ">New<" not in second.content.decode()
    read_at = SupportReply.objects.get().read_at
    assert read_at is not None and abs(read_at - NOW) < timedelta(seconds=5)


def test_reply_body_escaped_with_line_breaks(client: Any, student: User) -> None:
    SupportReplyFactory.create(
        request=SupportRequestFactory.create(sender=student),
        body="<script>alert(1)</script>\nline two",
    )
    html = client.get(REPLIES).content.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;<br>line two" in html


def test_other_students_replies_not_listed_or_counted(client: Any, student: User) -> None:
    SupportReplyFactory.create(body="Someone else's answer")
    html = client.get(REPLIES).content.decode()
    assert "Someone else" not in html
    response = client.get(FORM)
    help_item = response.context["nav_secondary"][0]
    assert help_item["count"] == 0
    assert SupportReply.objects.get().read_at is None


def test_help_nav_shows_unread_count(client: Any, student: User) -> None:
    SupportReplyFactory.create_batch(2, request=SupportRequestFactory.create(sender=student))
    response = client.get("/me/")
    assert response.context["nav_secondary"][0]["count"] == 2


def test_replies_paginate_25(client: Any, student: User) -> None:
    SupportReplyFactory.create_batch(26, request=SupportRequestFactory.create(sender=student))
    response = client.get(REPLIES)
    assert len(response.context["page"].object_list) == 25


def test_program_field_hint(client: Any, student: User) -> None:
    html = client.get(FORM).content.decode()
    assert (
        "Messages about a program go to that program&#x27;s staff and the scholarship office."
        in html
    )
