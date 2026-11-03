"""Every URL name is classified here, and every persona is checked against its rule (spec 6)."""

from typing import Any

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

PERSONAS = ["anonymous", "student", "other_student", "staff", "other_staff", "head", "office"]
RULES: dict[str, dict[str, Any]] = {
    "public": {p: "ok" for p in PERSONAS},
    "signed_in": {"anonymous": "login", **{p: "ok" for p in PERSONAS[1:]}},
    "student": {
        "anonymous": "login",
        "student": 200,
        "other_student": 200,
        "staff": 403,
        "other_staff": 403,
        "head": 403,
        "office": 403,
    },
    "staff": {
        "anonymous": "login",
        "student": 403,
        "other_student": 403,
        "staff": 200,
        "other_staff": 403,
        "head": 200,
        "office": 200,
    },
    "office": {
        "anonymous": "login",
        **{p: 403 for p in PERSONAS[1:6]},
        "office": 200,
    },
    "kit": {p: 404 for p in PERSONAS},
    # Confirm page for signed-in users; a signed-out visit has nothing to sign out of and goes home.
    "logout": {"anonymous": 302, **{p: 200 for p in PERSONAS[1:]}},
    # Steps of a sign-in or sign-up in progress: with none in progress, everyone is redirected.
    "flow_redirect": {p: 302 for p in PERSONAS},
    # allauth answers a GET without its state or token with 401, whoever asks.
    "error_401": {p: 401 for p in PERSONAS},
}
URLS: dict[str, str] = {
    "core:home": "public",
    "core:healthz": "public",
    "core:about": "public",
    "core:privacy": "public",
    "core:terms": "public",
    "core:cookies": "public",
    "core:help": "public",
    "core:contact": "public",
    "students:home": "student",
    "workspace:no_programs": "signed_in",
    "workspace:dashboard": "staff",
    "office:home": "office",
    "account_login": "public",
    "account_signup": "public",
    "account_logout": "logout",
    "account_inactive": "public",
    "account_reset_password": "public",
    "account_reset_password_done": "public",
    "account_reset_password_from_key": "public",
    "account_reset_password_from_key_done": "public",
    "account_confirm_email": "public",
    "account_email_verification_sent": "public",
    "account_confirm_login_code": "flow_redirect",
    "account_email": "signed_in",
    "account_change_password": "signed_in",
    "account_set_password": "signed_in",
    "account_reauthenticate": "signed_in",
    "google_login": "public",
    "google_callback": "error_401",
    "google_login_by_token": "error_401",
    "socialaccount_connections": "signed_in",
    "socialaccount_login_cancelled": "public",
    "socialaccount_login_error": "error_401",
    "socialaccount_signup": "flow_redirect",
    "kit:index": "kit",
    "kit:demo-toast": "kit",
    "kit:demo-dialog": "kit",
    "kit:demo-bulk": "kit",
    "kit:mockups": "kit",
    "kit:mockup": "kit",
    "kit:layout": "kit",
    "kit:demo-signout": "kit",
}
URL_KWARGS: dict[str, dict[str, str]] = {
    "workspace:dashboard": {"program": "tcu-ceaa"},
    "kit:mockup": {"slug": "x"},
    "kit:layout": {"name": "x"},
    # An unknown key shows allauth's invalid-link page (200), it does not 404.
    "account_confirm_email": {"key": "x"},
    "account_reset_password_from_key": {"uidb36": "1", "key": "x"},
}


def _collect(patterns: Any, prefix: str = "") -> set[str]:
    names: set[str] = set()
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = f"{prefix}{entry.namespace}:" if entry.namespace else prefix
            names |= _collect(entry.url_patterns, ns)
        elif isinstance(entry, URLPattern) and entry.name:
            names.add(f"{prefix}{entry.name}")
    return names


def test_every_url_is_in_the_matrix() -> None:
    found = _collect(get_resolver().url_patterns)
    missing, extra = sorted(found - set(URLS)), sorted(set(URLS) - found)
    assert not missing and not extra, f"not in the matrix: {missing}; not in the URLconf: {extra}"


@pytest.fixture(autouse=True)
def _google_configured(settings: Any) -> None:
    """Google sign-in is off without credentials; give it some so its URLs can be checked."""
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"APPS": [{"client_id": "id", "secret": "x"}]}}


@pytest.fixture
def personas(db: Any) -> dict[str, User | None]:
    tcu = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    lani = ProgramFactory.create(slug="lani", name="LANI")
    return {
        "anonymous": None,
        "student": UserFactory.create(verified=True),
        "other_student": UserFactory.create(verified=True),
        "staff": MembershipFactory.create(program=tcu, user__verified=True).user,
        "other_staff": MembershipFactory.create(program=lani, user__verified=True).user,
        "head": MembershipFactory.create(
            program=tcu, level=ProgramMembership.Level.HEAD, user__verified=True
        ).user,
        "office": UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True),
    }


@pytest.mark.parametrize("persona", PERSONAS)
@pytest.mark.parametrize("name", sorted(URLS))
def test_access(name: str, persona: str, client: Any, personas: dict[str, User | None]) -> None:
    user = personas[persona]
    if user is not None:
        client.force_login(user)
    url = reverse(name, kwargs=URL_KWARGS.get(name))
    response = client.get(url)
    expected = RULES[URLS[name]][persona]
    if expected == "login":
        assert response.status_code == 302, url
        assert response.url.startswith(reverse("account_login")), url
        assert "next=" in response.url, url
    elif expected == "ok":
        assert response.status_code < 400, (url, response.status_code)
    else:
        assert response.status_code == expected, (url, response.status_code)


def test_unknown_program_is_404_for_staff(client: Any, personas: dict[str, User | None]) -> None:
    client.force_login(personas["staff"])
    assert client.get("/staff/no-such-program/").status_code == 404
    client.force_login(personas["office"])
    assert client.get("/staff/no-such-program/").status_code == 404
