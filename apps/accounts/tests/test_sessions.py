"""Session rotation, the session list and ending sessions (M13)."""

from io import StringIO

import pytest
from allauth.usersessions.models import UserSession
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.models import AuditEvent
from apps.core.tests.auth import replay_after_password, signed_in_long_ago
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from conftest import HttpsClient

pytestmark = pytest.mark.django_db


def _sign_in(client: Client, user: User) -> Client:
    response = client.post(
        reverse("account_login"), {"login": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 302
    return client


def _signed_in_as(user: User) -> set[str]:
    return {
        s.session_key
        for s in Session.objects.all()
        if s.get_decoded().get("_auth_user_id") == str(user.pk)
    }


def test_reauthentication_cycles_the_session_key(client: Client) -> None:
    user = UserFactory.create(verified=True)
    _sign_in(client, user)
    before = client.session.session_key
    response = client.post(reverse("account_reauthenticate"), {"password": DEFAULT_PASSWORD})
    assert response.status_code == 302
    after = client.session.session_key
    assert after != before
    assert not Session.objects.filter(session_key=before).exists()
    assert client.session["_auth_user_id"] == str(user.pk)
    # The session list follows the new key.
    assert UserSession.objects.filter(user=user, session_key=after).exists()
    assert not UserSession.objects.filter(session_key=before).exists()


def test_user_lists_and_ends_other_sessions(client: Client) -> None:
    user = UserFactory.create(verified=True)
    other = _sign_in(HttpsClient(), user)
    _sign_in(client, user)
    page = client.get(reverse("usersessions_list"))
    assert page.status_code == 200
    assert page.context["session_count"] == 2
    assert b"Sign out other sessions" in page.content
    # Old enough that the post asks for the password again.
    session = client.session
    session.pop("account_authentication_methods", None)
    session.save()
    response = client.post(reverse("usersessions_list"))
    assert "reauthenticate" in response["Location"]
    replay = replay_after_password(client, response)
    assert replay.status_code == 302
    assert _signed_in_as(user) == {client.session.session_key}
    assert other.get(reverse("usersessions_list")).status_code == 302


def test_office_signs_staff_out_everywhere_after_password(client: Client) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    _sign_in(HttpsClient(), staff)
    _sign_in(HttpsClient(), staff)
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    signed_in_long_ago(client, office)
    response = client.post(reverse("office:staff-sessions", args=[staff.pk]))
    assert "reauthenticate" in response["Location"]
    replay = replay_after_password(client, response)
    assert replay.status_code == 302
    assert _signed_in_as(staff) == set()
    event = AuditEvent.objects.get(action="user.sessions_ended")
    assert event.actor == office
    assert event.data == {"account": staff.pk, "sessions_ended": 2}
    # The office's own session is untouched.
    assert client.session["_auth_user_id"] == str(office.pk)


def test_office_page_offers_sign_out_everywhere_for_others_only(client: Client) -> None:
    from apps.core.tests.auth import reauthenticated

    staff = UserFactory.create(role=User.Role.STAFF, verified=True)
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    reauthenticated(client, office)
    assert (
        b"Sign out everywhere"
        in client.get(reverse("office:staff-detail", args=[staff.pk])).content
    )
    own = client.get(reverse("office:staff-detail", args=[office.pk]))
    assert b"Sign out everywhere" not in own.content


def test_end_sessions_command_by_email_audited() -> None:
    student = UserFactory.create(verified=True)
    _sign_in(HttpsClient(), student)
    out = StringIO()
    call_command("end_sessions", "--email", f"  {student.email.upper()} ", stdout=out)
    assert f"account {student.pk}" in out.getvalue()
    assert student.email not in out.getvalue()
    assert _signed_in_as(student) == set()
    event = AuditEvent.objects.get(action="user.sessions_ended")
    assert event.actor is None
    assert event.data == {"account": student.pk, "sessions_ended": 1}
    assert student.email not in str(event.data)


def test_end_sessions_command_unknown_email() -> None:
    with pytest.raises(CommandError):
        call_command("end_sessions", "--email", "nobody@example.invalid")
