"""Two-factor sign-in (M13, ASVS V6.3.3)."""

from pathlib import Path
from typing import Any

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
    yield_hotp_counters_from_time,
)
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from config.tests.test_settings import settings_values

pytestmark = pytest.mark.django_db

ACTIVATE = "/accounts/2fa/totp/activate/"


@pytest.fixture
def required(settings: Any) -> None:
    settings.MFA_REQUIRED_FOR_STAFF = True


def _code(secret: str) -> str:
    counter = next(yield_hotp_counters_from_time())
    return str(format_hotp_value(hotp_value(secret, counter)))


def _staff() -> User:
    program = ProgramFactory.create(slug="tcu-ceaa")
    return MembershipFactory.create(program=program, user__verified=True).user


def test_staff_without_authenticator_is_sent_to_activation(client: Any, required: None) -> None:
    client.force_login(_staff())
    response = client.get("/staff/tcu-ceaa/")
    assert response.status_code == 302 and response["Location"] == ACTIVATE
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True))
    assert client.get("/office/")["Location"] == ACTIVATE


def test_student_is_not_required(client: Any, required: None, vite_build: Any) -> None:
    client.force_login(UserFactory.create(verified=True))
    assert client.get("/me/").status_code == 200


def test_only_mfa_and_logout_answer_until_activated(
    client: Any, required: None, vite_build: Any
) -> None:
    client.force_login(_staff())
    # allauth asks for the password before showing a new secret; both pages answer.
    activate = client.get(ACTIVATE)
    assert activate.status_code == 200 or "/accounts/reauthenticate/" in activate["Location"]
    assert client.get("/accounts/reauthenticate/").status_code == 200
    assert client.get("/accounts/password/change/")["Location"] == ACTIVATE
    response = client.post("/accounts/logout/")
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_htmx_request_gets_hx_redirect(client: Any, required: None) -> None:
    client.force_login(_staff())
    response = client.get("/staff/tcu-ceaa/applications/", headers={"HX-Request": "true"})
    assert response["HX-Redirect"] == ACTIVATE


def test_totp_sign_in_round_trip(client: Any, required: None, vite_build: Any) -> None:
    staff = _staff()
    secret = generate_totp_secret()
    TOTP.activate(staff, secret)
    response = client.post("/accounts/login/", {"login": staff.email, "password": DEFAULT_PASSWORD})
    assert response.status_code == 302 and response["Location"] == "/accounts/2fa/authenticate/"
    response = client.post("/accounts/2fa/authenticate/", {"code": _code(secret)})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(staff.pk)
    assert client.get("/staff/tcu-ceaa/").status_code == 200


def test_office_removes_a_staff_authenticator_after_password(client: Any) -> None:
    from apps.core.tests.auth import replay_after_password, signed_in_long_ago

    staff = _staff()
    TOTP.activate(staff, generate_totp_secret())
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    signed_in_long_ago(client, office)
    response = client.post(reverse("office:staff-mfa", args=[staff.pk]))
    assert "reauthenticate" in response["Location"]
    replay = replay_after_password(client, response)
    assert replay.status_code == 302
    assert not Authenticator.objects.filter(user=staff).exists()
    event = AuditEvent.objects.get(action="mfa.removed")
    assert event.data == {"account": staff.pk}


def test_requirement_off_in_developer_and_explore_modes(tmp_path: Path) -> None:
    unset = ["MFA_REQUIRED_FOR_STAFF"]
    assert settings_values(
        tmp_path, ["MFA_REQUIRED_FOR_STAFF"], DJANGO_DEBUG="true", _unset=unset
    ) == {"MFA_REQUIRED_FOR_STAFF": False}
    assert settings_values(tmp_path, ["MFA_REQUIRED_FOR_STAFF"], _unset=unset) == {
        "MFA_REQUIRED_FOR_STAFF": True
    }


def test_developer_copy_with_example_line_does_not_require(tmp_path: Path) -> None:
    values = settings_values(
        tmp_path, ["MFA_REQUIRED_FOR_STAFF"], DJANGO_DEBUG="true", MFA_REQUIRED_FOR_STAFF="true"
    )
    assert values == {"MFA_REQUIRED_FOR_STAFF": False}


def test_staff_cannot_switch_off_their_own_authenticator(client: Any, required: None) -> None:
    from apps.core.tests.auth import reauthenticated

    staff = _staff()
    TOTP.activate(staff, generate_totp_secret())
    reauthenticated(client, staff)
    response = client.post("/accounts/2fa/totp/deactivate/")
    assert Authenticator.objects.filter(user=staff, type=Authenticator.Type.TOTP).exists()
    assert response.status_code == 200  # the form, with allauth's refusal


def test_student_can_switch_off_and_it_is_audited(client: Any, required: None) -> None:
    from apps.core.tests.auth import reauthenticated

    student = UserFactory.create(verified=True)
    TOTP.activate(student, generate_totp_secret())
    reauthenticated(client, student)
    response = client.post("/accounts/2fa/totp/deactivate/")
    assert response.status_code == 302
    assert not Authenticator.objects.filter(user=student, type=Authenticator.Type.TOTP).exists()
    event = AuditEvent.objects.get(action="mfa.deactivated")
    assert event.actor == student
    assert event.data == {"type": "totp"}


def test_removed_authenticator_clears_the_cached_requirement(client: Any, settings: Any) -> None:
    from apps.accounts.mfa_policy import SESSION_KEY
    from apps.core.tests.auth import reauthenticated

    settings.MFA_REQUIRED_FOR_STAFF = False  # deletion allowed, then the requirement switches on
    staff = _staff()
    TOTP.activate(staff, generate_totp_secret())
    reauthenticated(client, staff)
    session = client.session
    session[SESSION_KEY] = True
    session.save()
    assert client.post("/accounts/2fa/totp/deactivate/").status_code == 302
    assert SESSION_KEY not in client.session
    settings.MFA_REQUIRED_FOR_STAFF = True
    response = client.get("/staff/tcu-ceaa/")
    assert response.status_code == 302 and response["Location"] == ACTIVATE


def test_activating_through_the_page_queues_the_notice(
    client: Any, required: None, django_capture_on_commit_callbacks: Any
) -> None:
    """The real page, with commit callbacks run: allauth's security email must have an outbox
    kind, or activation would fail after the commit."""
    from apps.core.tests.auth import reauthenticated
    from apps.workspace.models import EmailOutbox

    staff = _staff()
    reauthenticated(client, staff)
    client.get(ACTIVATE)  # stores the pending secret in the session
    from allauth.mfa.totp.internal.auth import SECRET_SESSION_KEY

    secret = client.session[SECRET_SESSION_KEY]
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(ACTIVATE, {"code": _code(secret)})
    assert response.status_code == 302
    assert Authenticator.objects.filter(user=staff, type=Authenticator.Type.TOTP).exists()
    assert EmailOutbox.objects.filter(kind="totp_activated").exists()
    assert AuditEvent.objects.filter(action="mfa.added", data={"type": "totp"}).exists()
