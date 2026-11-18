"""Idle and absolute session limits with a warning (M13; ASVS V7.3.1, V7.3.2;
WCAG 2.2.1)."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.get_default_timezone())
KEEP_ALIVE = "/accounts/session/keep-alive/"


def _sign_in(client: Any, user: User) -> None:
    response = client.post("/accounts/login/", {"login": user.email, "password": DEFAULT_PASSWORD})
    assert response.status_code == 302


def _staff() -> User:
    program = ProgramFactory.create(slug="tcu-ceaa")
    return MembershipFactory.create(program=program, user__verified=True).user


def test_staff_idle_31_minutes_is_signed_out_with_message(
    client: Any, time_machine: Any, vite_build: Any
) -> None:
    time_machine.move_to(START)
    _sign_in(client, _staff())
    assert client.get("/staff/tcu-ceaa/").status_code == 200
    time_machine.move_to(START + timedelta(minutes=31))
    response = client.get("/staff/tcu-ceaa/applications/")
    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=")
    assert "_auth_user_id" not in client.session
    page = client.get(response["Location"]).content.decode()
    assert "You were signed out after a period of inactivity." in page


def test_student_idle_59_minutes_is_still_signed_in(
    client: Any, time_machine: Any, vite_build: Any
) -> None:
    time_machine.move_to(START)
    _sign_in(client, UserFactory.create(verified=True))
    client.get("/me/")
    time_machine.move_to(START + timedelta(minutes=59))
    assert client.get("/me/").status_code == 200


def test_absolute_12_hours_ends_session_even_when_active(
    client: Any, time_machine: Any, vite_build: Any
) -> None:
    time_machine.move_to(START)
    _sign_in(client, UserFactory.create(verified=True))
    for minutes in range(0, 12 * 60, 50):
        time_machine.move_to(START + timedelta(minutes=minutes))
        assert client.get("/me/").status_code == 200, minutes
    time_machine.move_to(START + timedelta(hours=12, minutes=1))
    response = client.get("/me/")
    assert response.status_code == 302
    page = client.get(response["Location"]).content.decode()
    assert "You were signed out after 12 hours. Sign in again." in page


def test_keep_alive_resets_idle_and_answers_204(client: Any, time_machine: Any) -> None:
    time_machine.move_to(START)
    _sign_in(client, _staff())
    time_machine.move_to(START + timedelta(minutes=25))
    assert client.post(KEEP_ALIVE).status_code == 204
    time_machine.move_to(START + timedelta(minutes=50))
    assert client.get("/staff/tcu-ceaa/").status_code == 200


def test_responses_carry_the_idle_seconds_left(client: Any, time_machine: Any) -> None:
    time_machine.move_to(START, tick=False)
    _sign_in(client, _staff())
    client.get("/staff/tcu-ceaa/")
    time_machine.move_to(START + timedelta(seconds=30), tick=False)
    assert client.get("/staff/tcu-ceaa/")["X-Session-Idle"] == "1770"
    assert client.post(KEEP_ALIVE)["X-Session-Idle"] == "1800"


def test_status_check_is_not_activity(client: Any, time_machine: Any) -> None:
    """The warning script's own check can't keep an unattended tab signed in."""
    time_machine.move_to(START, tick=False)
    _sign_in(client, _staff())
    client.get("/staff/tcu-ceaa/")
    time_machine.move_to(START + timedelta(minutes=29), tick=False)
    response = client.get("/accounts/session/status/")
    assert response.json() == {"idle": 60, "absolute": 12 * 3600 - 29 * 60}
    time_machine.move_to(START + timedelta(minutes=31), tick=False)
    response = client.get("/accounts/session/status/")
    assert response.status_code == 302 and response["Location"].startswith("/accounts/login/")


def test_keep_alive_needs_post_and_sign_in(client: Any) -> None:
    assert client.post(KEEP_ALIVE)["Location"].startswith("/accounts/login/")
    client.force_login(UserFactory.create(verified=True))
    assert client.get(KEEP_ALIVE).status_code == 405


def test_last_activity_written_at_most_once_a_minute(
    client: Any, time_machine: Any, django_assert_max_num_queries: Any, vite_build: Any
) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    time_machine.move_to(START)
    _sign_in(client, UserFactory.create(verified=True))
    client.get("/me/")

    def session_writes() -> int:
        with CaptureQueriesContext(connection) as queries:
            client.get("/me/")
        return sum(
            1 for query in queries if "django_session" in query["sql"] and "UPDATE" in query["sql"]
        )

    time_machine.move_to(START + timedelta(seconds=20))
    assert session_writes() == 0
    time_machine.move_to(START + timedelta(seconds=90))
    assert session_writes() == 1


def test_htmx_gets_hx_redirect(client: Any, time_machine: Any) -> None:
    time_machine.move_to(START)
    _sign_in(client, _staff())
    time_machine.move_to(START + timedelta(minutes=40))
    response = client.get("/staff/tcu-ceaa/applications/", headers={"HX-Request": "true"})
    assert response["HX-Redirect"].startswith("/accounts/login/?next=")


def test_pages_carry_the_remaining_seconds(client: Any, time_machine: Any, vite_build: Any) -> None:
    time_machine.move_to(START, tick=False)
    _sign_in(client, _staff())
    html = client.get("/staff/tcu-ceaa/").content.decode()
    assert '<meta name="session-idle-seconds" content="1800">' in html
    assert '<meta name="session-absolute-seconds" content="43200">' in html
    assert reverse("session_keep_alive") in html
