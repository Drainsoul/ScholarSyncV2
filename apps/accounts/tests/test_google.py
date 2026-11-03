"""Google sign-in through allauth's own completion flow (complete_login), with a mocked Google
response: staff and scholarship-office accounts are never reachable through Google."""

from typing import Any

import pytest
from allauth.account.internal.flows.login import record_authentication
from allauth.core.context import request_context
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.internal.flows.login import complete_login
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory

PRIVILEGED = [
    {"role": User.Role.STAFF},
    {"role": User.Role.SUPER_ADMIN},
    {"is_staff": True},
    {"is_superuser": True},
]


@pytest.fixture(autouse=True)
def _google(settings: Any) -> None:
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APPS": [{"client_id": "test-client", "secret": "test-secret"}],
            "SCOPE": ["profile", "email"],
        }
    }


def _request(rf: RequestFactory, user: Any = None) -> HttpRequest:
    request = rf.get("/accounts/google/login/callback/", secure=True)
    SessionMiddleware(lambda r: HttpResponse()).process_request(request)
    request.session.save()
    request.user = user or AnonymousUser()
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    if user is not None:
        # A fresh password sign-in, so connecting needs no reauthentication first.
        record_authentication(request, user, "password", email=user.email, reauthenticated=True)
    return request


def _google_login(
    request: HttpRequest, *, email: str, uid: str = "g-100", process: str = "login"
) -> Any:
    """What allauth's Google callback builds from Google's userinfo response."""
    provider = get_adapter().get_provider(request, "google")
    response = {"sub": uid, "email": email, "email_verified": True, "name": "Gina Reyes"}
    sociallogin = provider.sociallogin_from_response(request, response)
    sociallogin.state = {"process": process}
    return sociallogin


def _complete(request: HttpRequest, sociallogin: Any) -> Any:
    with request_context(request):
        return complete_login(request, sociallogin)


def _signed_in(request: HttpRequest) -> bool:
    return "_auth_user_id" in request.session


@pytest.mark.parametrize("fields", PRIVILEGED)
def test_an_existing_google_link_never_signs_in_a_privileged_account(
    db: Any, rf: RequestFactory, fields: dict[str, Any]
) -> None:
    boss = UserFactory.create(email="boss@scholarsync.test", verified=True, **fields)
    SocialAccount.objects.create(user=boss, provider="google", uid="g-100")
    request = _request(rf)
    # The Google address differs, so only the stored link (not an email match) finds the user.
    response = _complete(request, _google_login(request, email="other@scholarsync.test"))
    assert response.status_code == 302 and response.url == "/accounts/login/"
    assert not _signed_in(request)
    assert [str(m) for m in get_messages(request)]


@pytest.mark.parametrize("fields", PRIVILEGED)
def test_a_google_email_match_never_signs_in_a_privileged_account(
    db: Any, rf: RequestFactory, fields: dict[str, Any]
) -> None:
    boss = UserFactory.create(email="boss@scholarsync.test", verified=True, **fields)
    request = _request(rf)
    response = _complete(request, _google_login(request, email="boss@scholarsync.test"))
    assert response.status_code == 302 and response.url == "/accounts/login/"
    assert not _signed_in(request)
    assert not SocialAccount.objects.filter(user=boss).exists()  # nor auto-connected
    boss.refresh_from_db()
    assert boss.has_usable_password()  # nor its password wiped


@pytest.mark.parametrize("fields", PRIVILEGED)
def test_a_privileged_account_cannot_connect_google(
    db: Any, rf: RequestFactory, fields: dict[str, Any]
) -> None:
    boss = UserFactory.create(email="boss@scholarsync.test", verified=True, **fields)
    request = _request(rf, user=boss)
    response = _complete(
        request, _google_login(request, email="gmail@scholarsync.test", process="connect")
    )
    assert response.status_code == 302 and "/accounts/3rdparty/" not in response.url
    assert not SocialAccount.objects.exists()
    assert [str(m) for m in get_messages(request)]


def test_a_student_signs_in_with_an_existing_google_link(db: Any, rf: RequestFactory) -> None:
    student = UserFactory.create(email="kid@scholarsync.test", verified=True)
    SocialAccount.objects.create(user=student, provider="google", uid="g-100")
    request = _request(rf)
    response = _complete(request, _google_login(request, email="kid@scholarsync.test"))
    assert response.status_code == 302 and response.url != "/accounts/login/"
    assert request.session["_auth_user_id"] == str(student.pk)


def test_a_student_signs_in_by_google_email_and_is_connected(db: Any, rf: RequestFactory) -> None:
    student = UserFactory.create(email="kid@scholarsync.test", verified=True)
    request = _request(rf)
    response = _complete(request, _google_login(request, email="kid@scholarsync.test"))
    assert response.status_code == 302
    assert request.session["_auth_user_id"] == str(student.pk)
    assert SocialAccount.objects.filter(user=student, provider="google").exists()


def test_a_student_can_connect_google(db: Any, rf: RequestFactory) -> None:
    student = UserFactory.create(email="kid@scholarsync.test", verified=True)
    request = _request(rf, user=student)
    response = _complete(
        request, _google_login(request, email="gmail@scholarsync.test", process="connect")
    )
    assert response.url == "/accounts/3rdparty/"
    assert SocialAccount.objects.filter(user=student, provider="google").exists()
