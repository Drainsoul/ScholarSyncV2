from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ConsentRecord
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import MembershipFactory
from apps.students.models import ProfileInvite, StudentProfile
from apps.students.selectors import INVALID_LINK
from apps.students.services import create_staff_profile
from apps.students.tests.factories import ProfileFactory
from apps.workspace.models import EmailOutbox
from conftest import HttpsClient

pytestmark = pytest.mark.django_db

EMAIL = "paolo@example.com"
EXPIRED = INVALID_LINK


def _setup() -> tuple[StudentProfile, str]:
    membership = MembershipFactory.create()
    profile, _ = create_staff_profile(
        actor=membership.user,
        program=membership.program,
        first_name="Paolo",
        middle_name="",
        last_name="Villanueva",
        suffix="",
        birth_date=date(2007, 5, 1),
        email=EMAIL,
    )
    row = EmailOutbox.objects.filter(kind="profile_invite").latest("pk")
    return profile, str(row.context["claim_url"]).rstrip("/").rsplit("/", 1)[-1]


def _url(token: str) -> str:
    return reverse("claim:start", args=[token])


def _signed_in(email: str = EMAIL) -> HttpsClient:
    user = UserFactory.create(email=email, verified=True)
    client = HttpsClient()
    client.force_login(user)
    return client


def test_unknown_token_is_the_404_page(client: HttpsClient) -> None:
    response = client.get(_url("nope"))
    assert response.status_code == 404
    assert "Page not found" in response.content.decode()


def test_anonymous_sees_masked_address_and_sign_in_buttons(client: HttpsClient) -> None:
    _, token = _setup()
    response = client.get(_url(token))
    body = response.content.decode()
    assert response.status_code == 200
    assert "p•••@example.com" in body
    assert EMAIL not in body
    assert "Sign in or create an account with the email address this invitation was sent to" in body
    assert "then open this link again." in body
    assert f'href="{reverse("account_login")}?next={_url(token)}"' in body
    assert f'href="{reverse("account_signup")}?next={_url(token)}"' in body
    assert "Claim profile" not in body


def test_response_is_not_cached_and_never_sends_the_path_as_referrer(client: HttpsClient) -> None:
    _, token = _setup()
    for path in (_url(token), _url("nope")):
        response = client.get(path)
        assert "no-store" in response["Cache-Control"]
        assert response["Referrer-Policy"] == "strict-origin"


def test_signed_in_with_the_invited_address_sees_the_form() -> None:
    _, token = _setup()
    response = _signed_in().get(_url(token))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Claim the profile for Paolo Villanueva?" in body
    assert "agree to ScholarSync keeping my information for my scholarship applications." in body
    assert "I have read the" in body
    assert 'href="/privacy/"' in body
    assert "Claim profile" in body


def test_a_different_address_sees_the_reason_and_no_form() -> None:
    _, token = _setup()
    body = _signed_in("other@example.com").get(_url(token)).content.decode()
    assert "This invitation was sent to a different email address." in body
    assert "Claim profile" not in body


def test_post_without_the_box_shows_the_field_error() -> None:
    profile, token = _setup()
    client = _signed_in()
    response = client.post(_url(token), {})
    assert response.status_code == 200
    assert "This field is required." in response.content.decode()
    profile.refresh_from_db()
    assert profile.user_id is None


def test_post_claims_and_redirects_with_a_message() -> None:
    profile, token = _setup()
    client = _signed_in()
    response = client.post(_url(token), {"consent": "on"}, follow=True)
    assert response.redirect_chain[-1][0] == reverse("students:profile")
    assert "Profile claimed. Check that your details are right." in response.content.decode()
    profile.refresh_from_db()
    assert profile.user is not None
    assert profile.user.email == EMAIL
    assert ConsentRecord.objects.filter(user=profile.user).exists()


def test_reusing_the_token_after_a_claim_shows_the_expired_sentence() -> None:
    _, token = _setup()
    _signed_in().post(_url(token), {"consent": "on"})
    other = _signed_in("another@example.com")
    assert EXPIRED in other.get(_url(token)).content.decode()
    body = other.post(_url(token), {"consent": "on"}).content.decode()
    assert EXPIRED in body


def test_an_expired_invite_shows_the_expired_sentence() -> None:
    _, token = _setup()
    ProfileInvite.objects.update(expires_at=timezone.now() - timedelta(days=1))
    assert EXPIRED in _signed_in().get(_url(token)).content.decode()


def test_a_validation_error_re_renders_with_its_message() -> None:
    profile, token = _setup()
    student = UserFactory.create(email=EMAIL, verified=True)
    client = HttpsClient()
    client.force_login(student)
    ProfileFactory.create(user=student)
    response = client.post(_url(token), {"consent": "on"})
    assert response.status_code == 200
    assert "Your account already has a profile." in response.content.decode()
    profile.refresh_from_db()
    assert profile.user_id is None


def test_the_token_never_appears_in_an_audit_event() -> None:
    _, token = _setup()
    _signed_in().post(_url(token), {"consent": "on"})
    assert AuditEvent.objects.filter(action="profile.claimed").exists()
    for event in AuditEvent.objects.all():
        assert token not in str(event.data)
        assert token not in str(event.__dict__)
