"""Support inboxes and the request page for the office and program staff (spec §12 rev 35)."""

from datetime import datetime
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.models import EmailOutbox, SupportReply, SupportRequest
from apps.workspace.tests.factories import (
    ReplyTemplateFactory,
    SupportReplyFactory,
    SupportRequestFactory,
)

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> Any:
    time_machine.move_to(NOW)
    return time_machine


@pytest.fixture
def program() -> Program:
    return ProgramFactory.create(name="LANI", slug="lani")


@pytest.fixture
def staff(client: Any, program: Program) -> User:
    user = UserFactory.create(role=User.Role.STAFF, full_name="Maria Santos")
    MembershipFactory.create(user=user, program=program)
    client.force_login(user)
    return user


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, full_name="Jessica Tate")
    client.force_login(user)
    return user


def _ask(**fields: Any) -> SupportRequest:
    fields.setdefault("sender", UserFactory.create(full_name="Ana Reyes"))
    return SupportRequestFactory.create(**fields)


def _staff_url(name: str, program: Program, **kw: Any) -> str:
    return reverse(f"workspace:{name}", kwargs={"program": program.slug, **kw})


def test_staff_inbox_shows_only_their_program(client: Any, staff: User, program: Program) -> None:
    _ask(program=program, message="Mine to answer")
    _ask(program=ProgramFactory.create(), message="Another program")
    _ask(message="Nobody's program")
    html = client.get(_staff_url("support", program)).content.decode()
    assert "Mine to answer" in html
    assert "Another program" not in html and "Nobody&#x27;s program" not in html


def test_office_inbox_shows_all_and_who_answered(client: Any, office: User) -> None:
    row = _ask(message="Answered one", program=ProgramFactory.create())
    row.status, row.answered_by, row.answered_at = "answered", office, NOW
    row.save()
    SupportReplyFactory.create_batch(2, request=row)
    _ask(message="Open one")
    assert "Open one" in client.get(reverse("support:office")).content.decode()
    html = client.get(reverse("support:office") + "?tab=answered").content.decode()
    assert "Answered by Jessica Tate · <time" in html
    assert ">21 Nov 2026, 10:00 AM</time>" in html
    assert "2 replies" in html


def test_cards_link_to_reply_and_email_forms(client: Any, office: User) -> None:
    row = _ask()
    html = client.get(reverse("support:office")).content.decode()
    detail = reverse("support:office-detail", args=[row.pk])
    assert f'href="{detail}#reply"' in html and f'href="{detail}#email"' in html
    assert f'hx-get="{detail}?form=reply"' in html and f'hx-get="{detail}?form=email"' in html
    assert "mailto:" not in html


def test_detail_lists_replies_with_author_channel_and_email_status(
    client: Any, office: User
) -> None:
    row = _ask()
    staff_author = UserFactory.create(role=User.Role.STAFF, full_name="Maria Santos")
    SupportReplyFactory.create(request=row, author=staff_author, body="In-app answer")
    sent = EmailOutbox.objects.create(to="a@example.com", kind="support_reply", status="sent")
    SupportReplyFactory.create(
        request=row, channel="email", subject="Re: hi", body="Email answer", email=sent
    )
    failed = EmailOutbox.objects.create(to="a@example.com", kind="support_reply", status="failed")
    bad = SupportReplyFactory.create(
        request=row, channel="email", subject="Re: lost", body="Lost answer", email=failed
    )
    detail = reverse("support:office-detail", args=[row.pk])
    html = client.get(detail).content.decode()
    assert "Maria Santos · In the app" in html
    assert ">Sent<" in html and ">Failed<" in html
    again = f"{detail}?form=email&amp;from={bad.pk}#email"
    assert f'href="{again}"' in html and "Write it again" in html
    refill = client.get(f"{detail}?form=email&from={bad.pk}")
    assert refill.context["email_form"].initial == {"subject": "Re: lost", "body": "Lost answer"}


def test_reply_post_saves_and_redirects_with_toast(client: Any, office: User) -> None:
    row = _ask()
    response = client.post(
        reverse("support:office-reply", args=[row.pk]), {"body": "Two weeks."}, follow=True
    )
    assert "Reply sent." in response.content.decode()
    assert SupportReply.objects.get().body == "Two weeks."


def test_email_post_toast_names_address(client: Any, office: User) -> None:
    row = _ask()
    response = client.post(
        reverse("support:office-email", args=[row.pk]),
        {"subject": "Re: your message", "body": "Two weeks."},
        follow=True,
    )
    assert f"Email queued to {row.sender.email}." in response.content.decode()
    assert EmailOutbox.objects.get().kind == "support_reply"


def test_subject_with_newline_refused(client: Any, office: User) -> None:
    row = _ask()
    response = client.post(
        reverse("support:office-email", args=[row.pk]),
        {"subject": "Hi\r\nBcc: x@example.com", "body": "Two weeks."},
    )
    assert response.status_code == 200
    assert "Enter the subject on one line." in response.content.decode()
    assert not SupportReply.objects.exists() and not EmailOutbox.objects.exists()


def test_cross_program_post_is_404_and_writes_nothing(
    client: Any, staff: User, program: Program
) -> None:
    for row in (_ask(program=ProgramFactory.create()), _ask()):
        for name, data in (
            ("support-reply", {"body": "x"}),
            ("support-email", {"subject": "s", "body": "x"}),
            ("support-answer", {}),
            ("support-detail", None),
        ):
            url = _staff_url(name, program, pk=row.pk)
            response = client.get(url) if data is None else client.post(url, data)
            assert response.status_code == 404, name
    assert not SupportReply.objects.exists()
    assert not SupportRequest.objects.filter(status="answered").exists()


def test_staff_reply_in_own_program(client: Any, staff: User, program: Program) -> None:
    row = _ask(program=program)
    client.post(_staff_url("support-reply", program, pk=row.pk), {"body": "Two weeks."})
    reply = SupportReply.objects.get()
    assert reply.author == staff
    client.post(_staff_url("support-answer", program, pk=_ask(program=program).pk))
    assert SupportRequest.objects.filter(status="answered").count() == 2


def test_compose_email_hidden_for_inactive_sender(client: Any, office: User) -> None:
    row = _ask(sender=UserFactory.create(is_active=False))
    html = client.get(reverse("support:office")).content.decode()
    assert "#email" not in html
    detail = client.get(reverse("support:office-detail", args=[row.pk])).content.decode()
    assert 'id="email"' not in detail and 'id="reply"' in detail


def test_use_template_without_js(client: Any, office: User) -> None:
    row = _ask(topic="allowance")
    template = ReplyTemplateFactory.create(subject="", body="Hi {first_name}.")
    detail = reverse("support:office-detail", args=[row.pk])
    response = client.get(f"{detail}?form=email&template={template.pk}")
    assert response.context["email_form"].initial == {
        "subject": "Re: your message about an allowance",
        "body": "Hi Ana.",
        "template": template.pk,
    }
    assert response.context["reply_form"].initial == {}


def test_template_options_carry_filled_text(client: Any, office: User) -> None:
    row = _ask(topic="allowance")
    template = ReplyTemplateFactory.create(title="Late", body="Hi {first_name} <b>")
    html = client.get(reverse("support:office-detail", args=[row.pk])).content.decode()
    assert f'value="{template.pk}" data-subject="Re: your message about an allowance"' in html
    assert 'data-body="Hi Ana &lt;b&gt;"' in html


def test_staff_nav_support_count_and_dashboard_row(
    client: Any, staff: User, program: Program
) -> None:
    _ask(program=program)
    _ask(program=program)
    _ask()
    response = client.get(_staff_url("dashboard", program))
    labels = [item["label"] for item in response.context["nav_items"]]
    assert labels.index("Support") == labels.index("Reports") + 1
    item = next(i for i in response.context["nav_items"] if i["label"] == "Support")
    assert item["count"] == 2
    html = response.content.decode()
    assert "2 support requests are waiting" in html
    assert _staff_url("support", program) in html


@pytest.mark.parametrize("who", ["office", "staff"])
def test_inbox_query_count(
    client: Any, program: Program, who: str, django_assert_max_num_queries: Any
) -> None:
    if who == "office":
        client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
        url = reverse("support:office")
    else:
        user = UserFactory.create(role=User.Role.STAFF)
        MembershipFactory.create(user=user, program=program)
        client.force_login(user)
        url = _staff_url("support", program)
    for _ in range(30):
        _ask(program=program)
    with django_assert_max_num_queries(16):
        assert client.get(url).status_code == 200


def test_email_to_a_closed_account_shows_why(client: Any, office: User) -> None:
    row = _ask()
    row.sender.is_active = False
    row.sender.save()
    response = client.post(
        reverse("support:office-email", args=[row.pk]), {"subject": "Re: hi", "body": "Two weeks."}
    )
    assert (
        "This student&#x27;s account is closed. Reply in the app instead."
        in response.content.decode()
    )
    assert not EmailOutbox.objects.exists()
