"""Every URL name is classified here, and every persona is checked against its rule (spec 6).

A rule gives, per persona, an exact status. A redirect is `(302, target)` where target is a path,
"home" (the persona's own role home) or "login" (the sign-in page carrying `next=<requested path>`).
"""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

PERSONAS = ["anonymous", "student", "other_student", "staff", "other_staff", "head", "office"]
SIGNED_IN = PERSONAS[1:]
HOMES = {
    "student": "/me/",
    "other_student": "/me/",
    "staff": "/staff/tcu-ceaa/",
    "other_staff": "/staff/lani/",
    "head": "/staff/tcu-ceaa/",
    "office": "/office/",
}
LOGIN = (302, "login")
HOME = (302, "home")
CHANGE_PASSWORD = (302, "/accounts/password/change/")
SIGN_IN_PAGE = (302, "/accounts/login/")

RULES: dict[str, dict[str, Any]] = {
    "public": {p: 200 for p in PERSONAS},
    # Sign in and sign up are for guests; anyone signed in is sent to their own home.
    "guest_only": {"anonymous": 200, **{p: HOME for p in SIGNED_IN}},
    "signed_in": {"anonymous": LOGIN, **{p: 200 for p in SIGNED_IN}},
    # Everyone here has a password, so allauth sends them to change it instead.
    "set_password": {"anonymous": LOGIN, **{p: CHANGE_PASSWORD for p in SIGNED_IN}},
    # /staff/ is for staff with no program; every persona here has a home elsewhere.
    "no_programs": {"anonymous": LOGIN, **{p: HOME for p in SIGNED_IN}},
    "student": {
        "anonymous": LOGIN,
        "student": 200,
        "other_student": 200,
        "staff": 403,
        "other_staff": 403,
        "head": 403,
        "office": 403,
    },
    "staff": {
        "anonymous": LOGIN,
        "student": 403,
        "other_student": 403,
        "staff": 200,
        "other_staff": 403,
        "head": 200,
        "office": 200,
    },
    # A program's application by id: the guards run first, then an id outside it is a 404.
    "staff_object": {
        "anonymous": LOGIN,
        "student": 403,
        "other_student": 403,
        "staff": 404,
        "other_staff": 403,
        "head": 404,
        "office": 404,
    },
    # A staff action that only answers POST: the guards run first, then a GET is 405.
    "staff_post_only": {
        "anonymous": LOGIN,
        "student": 403,
        "other_student": 403,
        "staff": 405,
        "other_staff": 403,
        "head": 405,
        "office": 405,
    },
    # A student action that only answers POST: the role guard runs, then a GET is 405.
    "student_post_only": {
        "anonymous": LOGIN,
        "student": 405,
        "other_student": 405,
        "staff": 403,
        "other_staff": 403,
        "head": 403,
        "office": 403,
    },
    "office": {"anonymous": LOGIN, **{p: 403 for p in PERSONAS[1:6]}, "office": 200},
    "kit": {p: 404 for p in PERSONAS},
    # An unknown claim link is a 404 for everyone.
    "claim_unknown": {p: 404 for p in PERSONAS},
    # A signed-out visit has nothing to sign out of and goes home; signed in gets the confirm page.
    "logout": {"anonymous": (302, "/"), **{p: 200 for p in SIGNED_IN}},
    # Next step of a sign-in by emailed code; with none in progress, back to the sign-in page.
    "login_code": {"anonymous": SIGN_IN_PAGE, **{p: HOME for p in SIGNED_IN}},
    "no_pending_signup": {p: SIGN_IN_PAGE for p in PERSONAS},
    # allauth answers a GET without its state or token with 401, whoever asks.
    "error_401": {p: 401 for p in PERSONAS},
    # Google is installed but has no credentials by default (explore mode, most self-hosters).
    "google_off": {p: 404 for p in PERSONAS},
    # Upload endpoints take POST only; a GET is 405 for everyone (an anonymous POST gets 401 JSON).
    "post_only": {p: 405 for p in PERSONAS},
    # Someone else's file, or an id that doesn't exist, is a 404 and reveals nothing.
    "own_file": {"anonymous": LOGIN, **{p: 404 for p in SIGNED_IN}},
    # A student's own row is theirs alone: any other id is a 404 (a missing row looks the same).
    "own_record": {
        "anonymous": LOGIN,
        "student": 404,
        "other_student": 404,
        "staff": 403,
        "other_staff": 403,
        "head": 403,
        "office": 403,
    },
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
    "programs:list": "public",
    "programs:detail": "public",
    "matching:match": "student",
    "applications:list": "student",
    "applications:new": "student",
    "applications:detail": "own_record",
    "applications:document": "student_post_only",
    "applications:submit": "student_post_only",
    "applications:withdraw": "own_record",
    "students:home": "student",
    "students:profile": "student",
    "students:profile-personal": "student",
    "students:profile-photo": "student",
    "students:profile-family": "student",
    "students:profile-family-add": "student",
    "students:profile-family-edit": "own_record",
    "students:profile-family-delete": "own_record",
    "students:profile-education": "student",
    "students:profile-education-add": "student",
    "students:profile-education-edit": "own_record",
    "students:profile-education-delete": "own_record",
    "workspace:no_programs": "no_programs",
    "workspace:dashboard": "staff",
    "workspace:students": "staff",
    "workspace:students-new": "staff",
    "workspace:students-invite": "staff_post_only",
    "review:queue": "staff",
    "review:bulk": "staff_post_only",
    "review:detail": "staff_object",
    "review:start": "staff_post_only",
    "review:document-approve": "staff_post_only",
    "review:document-decline": "staff_object",
    "review:decide": "staff_post_only",
    "review:behalf-new": "staff",
    "review:behalf": "staff_object",
    "review:behalf-academics": "staff_post_only",
    "review:behalf-document": "staff_post_only",
    "review:behalf-submit": "staff_post_only",
    "review:behalf-withdraw": "staff_post_only",
    "office:home": "office",
    "scholarships:list": "student",
    "scholars:list": "staff",
    "scholars:detail": "staff_object",
    "scholars:edit": "staff_object",
    "scholars:status": "staff_object",
    "scholarships:renew": "student_post_only",
    "account_login": "guest_only",
    "account_signup": "guest_only",
    "account_logout": "logout",
    "account_inactive": "public",
    "account_reset_password": "public",
    "account_reset_password_done": "public",
    "account_reset_password_from_key": "public",
    "account_reset_password_from_key_done": "public",
    "account_confirm_email": "public",
    "account_email_verification_sent": "public",
    "account_confirm_login_code": "login_code",
    "account_email": "signed_in",
    "account_change_password": "signed_in",
    "account_set_password": "set_password",
    "account_reauthenticate": "signed_in",
    "google_login": "google_off",
    "google_callback": "google_off",
    "google_login_by_token": "google_off",
    "socialaccount_connections": "signed_in",
    "socialaccount_login_cancelled": "public",
    "socialaccount_login_error": "error_401",
    "socialaccount_signup": "no_pending_signup",
    "kit:index": "kit",
    "kit:demo-toast": "kit",
    "kit:demo-dialog": "kit",
    "kit:demo-bulk": "kit",
    "kit:demo-upload": "kit",
    "kit:mockups": "kit",
    "kit:mockup": "kit",
    "kit:layout": "kit",
    "kit:demo-signout": "kit",
    "files:upload-intent": "post_only",
    "files:upload-confirm": "post_only",
    "files:download": "own_file",
    "claim:start": "claim_unknown",
}
URL_KWARGS: dict[str, dict[str, str]] = {
    "workspace:dashboard": {"program": "tcu-ceaa"},
    "workspace:students": {"program": "tcu-ceaa"},
    "scholarships:renew": {"pk": "999999"},
    "scholars:list": {"program": "tcu-ceaa"},
    "scholars:detail": {"program": "tcu-ceaa", "pk": "999999"},
    "scholars:edit": {"program": "tcu-ceaa", "pk": "999999"},
    "scholars:status": {"program": "tcu-ceaa", "pk": "999999"},
    "review:queue": {"program": "tcu-ceaa"},
    "review:bulk": {"program": "tcu-ceaa"},
    "review:detail": {"program": "tcu-ceaa", "pk": "999999"},
    "review:start": {"program": "tcu-ceaa", "pk": "999999"},
    "review:document-approve": {"program": "tcu-ceaa", "pk": "999999", "document": "999999"},
    "review:document-decline": {"program": "tcu-ceaa", "pk": "999999", "document": "999999"},
    "review:decide": {"program": "tcu-ceaa", "pk": "999999"},
    "review:behalf-new": {"program": "tcu-ceaa"},
    "review:behalf": {"program": "tcu-ceaa", "pk": "999999"},
    "review:behalf-academics": {"program": "tcu-ceaa", "pk": "999999"},
    "review:behalf-document": {"program": "tcu-ceaa", "pk": "999999", "requirement": "999999"},
    "review:behalf-submit": {"program": "tcu-ceaa", "pk": "999999"},
    "review:behalf-withdraw": {"program": "tcu-ceaa", "pk": "999999"},
    "workspace:students-new": {"program": "tcu-ceaa"},
    "workspace:students-invite": {"program": "tcu-ceaa", "profile_id": "999999"},
    "programs:detail": {"slug": "tcu-ceaa"},
    "applications:new": {"program": "tcu-ceaa"},
    "applications:detail": {"pk": "999999"},
    "applications:document": {"pk": "999999", "requirement": "999999"},
    "applications:submit": {"pk": "999999"},
    "applications:withdraw": {"pk": "999999"},
    "kit:mockup": {"slug": "x"},
    "kit:layout": {"name": "x"},
    "files:upload-confirm": {"file_id": "00000000-0000-0000-0000-000000000000"},
    "files:download": {"file_id": "00000000-0000-0000-0000-000000000000"},
    "claim:start": {"token": "unknown-token"},
    "students:profile-family-edit": {"pk": "999999"},
    "students:profile-family-delete": {"pk": "999999"},
    "students:profile-education-edit": {"pk": "999999"},
    "students:profile-education-delete": {"pk": "999999"},
    # An unknown key shows allauth's invalid-link page (200), it does not 404.
    "account_confirm_email": {"key": "x"},
    "account_reset_password_from_key": {"uidb36": "1", "key": "x"},
}


def _walk(patterns: Any, prefix: str = "", route: str = "") -> tuple[set[str], list[str]]:
    names: set[str] = set()
    unnamed: list[str] = []
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = f"{prefix}{entry.namespace}:" if entry.namespace else prefix
            found, missing = _walk(entry.url_patterns, ns, route + str(entry.pattern))
            names |= found
            unnamed += missing
        elif isinstance(entry, URLPattern):
            if entry.name:
                names.add(f"{prefix}{entry.name}")
            else:
                unnamed.append(route + str(entry.pattern))
    return names, unnamed


def test_every_url_is_in_the_matrix() -> None:
    found, unnamed = _walk(get_resolver().url_patterns)
    missing, extra = sorted(found - set(URLS)), sorted(set(URLS) - found)
    assert not missing and not extra, f"not in the matrix: {missing}; not in the URLconf: {extra}"
    # Only allauth's legacy permanent redirects (accounts/social/...) may go without a name.
    stray = [route for route in unnamed if not route.startswith("accounts/social/")]
    assert not stray, f"unnamed URL patterns would escape the matrix: {stray}"


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
    if isinstance(expected, int):
        assert response.status_code == expected, (url, response.status_code)
        return
    status, target = expected
    assert response.status_code == status, (url, response.status_code)
    location = urlsplit(response.url)
    if target == "login":
        assert location.path == reverse("account_login"), (url, response.url)
        assert parse_qs(location.query).get("next") == [url], (url, response.url)
    else:
        want = HOMES[persona] if target == "home" else target
        assert location.path == want, (url, response.url)


def test_no_programs_page_shows_for_staff_without_programs(client: Any, db: Any) -> None:
    client.force_login(UserFactory.create(role=User.Role.STAFF, verified=True))
    assert client.get("/staff/").status_code == 200


def test_google_with_keys_shows_confirm_page_and_rejects_a_bare_callback(
    client: Any, db: Any, settings: Any
) -> None:
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"APPS": [{"client_id": "id", "secret": "x"}]}}
    assert client.get(reverse("google_login")).status_code == 200
    assert client.get(reverse("google_callback")).status_code == 401


def test_unknown_program_is_404_for_staff(client: Any, personas: dict[str, User | None]) -> None:
    client.force_login(personas["staff"])
    assert client.get("/staff/no-such-program/").status_code == 404
    client.force_login(personas["office"])
    assert client.get("/staff/no-such-program/").status_code == 404
