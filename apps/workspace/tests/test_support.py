from datetime import datetime, timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import EmailOutbox, SupportRequest
from apps.workspace.tests.factories import SupportRequestFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 10, 0, tzinfo=TZ)
FORM = "/me/support/"
INBOX = "/office/support/"
LIMIT = "You've sent 5 messages today. The office will reply by email; try again tomorrow."


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> Any:
    time_machine.move_to(NOW)
    return time_machine


@pytest.fixture
def student(client: Any) -> User:
    user = UserFactory.create(full_name="Ana Reyes")
    client.force_login(user)
    return user


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _send(client: Any, message: str = "My allowance is late.", **extra: str) -> Any:
    return client.post(FORM, {"topic": "allowance", "message": message, **extra}, follow=True)


def test_student_sends_a_message(client: Any, student: User) -> None:
    program = ProgramFactory.create()
    response = _send(client, program=str(program.pk))
    assert "Message sent. The scholarship office will reply by email." in response.content.decode()
    row = SupportRequest.objects.get()
    assert (row.sender, row.topic, row.program, row.status) == (
        student,
        "allowance",
        program,
        SupportRequest.Status.OPEN,
    )
    event = AuditEvent.objects.get(action="support.sent")
    assert "late" not in str(event.data)
    assert event.data == {"topic": "allowance", "program": program.pk}
    assert not EmailOutbox.objects.exists()


def test_sixth_message_in_24_hours_is_refused_and_keeps_the_text(
    client: Any, student: User, _frozen: Any
) -> None:
    SupportRequestFactory.create_batch(5, sender=student)
    SupportRequest.objects.update(created_at=NOW - timedelta(hours=23))
    response = _send(client, message="Sixth try, please read")
    html = response.content.decode()
    assert response.status_code == 200
    assert LIMIT.replace("'", "&#x27;") in html
    assert "Sixth try, please read" in html
    assert SupportRequest.objects.count() == 5


def test_limit_window_slides(client: Any, student: User) -> None:
    SupportRequestFactory.create_batch(5, sender=student)
    SupportRequest.objects.update(created_at=NOW - timedelta(hours=24, minutes=1))
    _send(client)
    assert SupportRequest.objects.count() == 6


@pytest.mark.parametrize("message", ["   ", "x" * 2001])
def test_blank_and_too_long_message_rejected(client: Any, student: User, message: str) -> None:
    assert _send(client, message=message).status_code == 200
    assert not SupportRequest.objects.exists()


def test_inactive_program_not_offered(client: Any, student: User) -> None:
    ProgramFactory.create(name="Active One")
    gone = ProgramFactory.create(name="Gone Program", is_active=False)
    html = client.get(FORM).content.decode()
    assert "Active One" in html and "Gone Program" not in html
    _send(client, program=str(gone.pk))
    assert not SupportRequest.objects.exists()


def test_own_requests_listed_with_status(client: Any, student: User) -> None:
    SupportRequestFactory.create(sender=student, message="First question")
    SupportRequestFactory.create(
        sender=student, message="Second question", status=SupportRequest.Status.ANSWERED
    )
    SupportRequestFactory.create(message="Someone else's question")
    html = client.get(FORM).content.decode()
    assert "First question" in html and "Second question" in html
    assert "Someone else" not in html
    assert ">Waiting<" in html and ">Answered<" in html


def test_office_inbox_tabs_and_escaped_message(client: Any, office: User) -> None:
    sender = UserFactory.create(full_name="Ana Reyes")
    SupportRequestFactory.create(sender=sender, message="<script>alert(1)</script>\nline two")
    SupportRequestFactory.create(message="Done one", status=SupportRequest.Status.ANSWERED)
    html = client.get(INBOX).content.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;<br>line two" in html
    assert f'href="mailto:{sender.email}"' in html
    assert "Done one" not in html
    assert "Done one" in client.get(INBOX + "?tab=answered").content.decode()


def test_answer_marks_answered_once(client: Any, office: User) -> None:
    row = SupportRequestFactory.create()
    url = reverse("support:answer", args=[row.pk])
    assert client.post(url).status_code == 302
    client.post(url)
    row.refresh_from_db()
    assert (row.status, row.answered_by) == (SupportRequest.Status.ANSWERED, office)
    assert AuditEvent.objects.filter(action="support.answered").count() == 1


def test_answer_unknown_id_is_404(client: Any, office: User) -> None:
    assert client.post(reverse("support:answer", args=[999999])).status_code == 404


def test_office_nav_and_overview_count_open_requests(client: Any, office: User) -> None:
    SupportRequestFactory.create_batch(2)
    SupportRequestFactory.create(status=SupportRequest.Status.ANSWERED)
    response = client.get(reverse("office:home"))
    item = next(item for item in response.context["nav_items"] if item["label"] == "Support")
    assert item["count"] == 2
    html = response.content.decode()
    assert "2 support requests are waiting" in html
    board = response.context["board"]
    assert {"label": "Support requests", "value": "2"} not in board.figures  # M11c: reports


def test_student_help_link_in_secondary_nav(client: Any, student: User) -> None:
    response = client.get("/me/")
    (item,) = response.context["nav_secondary"]
    assert (item["label"], item["url"]) == ("Help and guides", FORM)


def test_inbox_query_count(client: Any, office: User, django_assert_max_num_queries: Any) -> None:
    SupportRequestFactory.create_batch(50)
    with django_assert_max_num_queries(12):
        assert client.get(INBOX).status_code == 200
