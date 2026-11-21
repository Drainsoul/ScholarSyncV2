"""Light, dark or the device's theme from the account menu (spec §12 rev 29)."""

import re

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = "/accounts/theme/"


def pressed(html: str) -> dict[str, str]:
    """Theme value -> its aria-pressed, from the first theme form on the page."""
    return dict(re.findall(r'name="theme" value="(\w+)" title="[^"]*" aria-pressed="(\w+)"', html))


def test_pinning_dark_sets_a_long_lived_http_only_cookie_and_returns_to_the_page(client: Client):
    response = client.post(URL, {"theme": "dark", "next": "/me/?tab=1"})
    assert response.status_code == 302
    assert response["Location"] == "/me/?tab=1"
    cookie = response.cookies[settings.THEME_COOKIE_NAME]
    assert cookie.value == "dark"
    assert cookie["max-age"] == 365 * 24 * 60 * 60
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    # The test settings force production security: the cookie is __Host- and Secure.
    assert settings.THEME_COOKIE_NAME == "__Host-theme"
    assert cookie["secure"]
    assert cookie["path"] == "/"
    assert not cookie["domain"]


def test_system_deletes_the_cookie(client: Client):
    client.cookies[settings.THEME_COOKIE_NAME] = "dark"
    response = client.post(URL, {"theme": "system", "next": "/"})
    assert response.cookies[settings.THEME_COOKIE_NAME].value == ""
    assert response.cookies[settings.THEME_COOKIE_NAME]["max-age"] == 0


def test_an_unknown_choice_changes_nothing(client: Client):
    response = client.post(URL, {"theme": "purple", "next": "/"})
    assert response.status_code == 302
    assert settings.THEME_COOKIE_NAME not in response.cookies


@pytest.mark.parametrize(
    "target", ["https://evil.example/", "//evil.example/", "javascript:alert(1)", ""]
)
def test_next_never_leaves_the_site(client: Client, target: str):
    response = client.post(URL, {"theme": "light", "next": target})
    assert response["Location"] == "/"


def test_get_is_not_allowed(client: Client):
    assert client.get(URL).status_code == 405


def test_the_page_follows_the_device_until_a_theme_is_pinned(client: Client):
    html = client.get("/accounts/login/").content.decode()
    assert '<html lang="en">' in html
    assert '<meta name="color-scheme" content="light dark">' in html

    client.cookies[settings.THEME_COOKIE_NAME] = "dark"
    html = client.get("/accounts/login/").content.decode()
    assert '<html lang="en" data-theme="dark">' in html
    assert '<meta name="color-scheme" content="dark">' in html


def test_a_tampered_cookie_is_ignored(client: Client):
    client.cookies[settings.THEME_COOKIE_NAME] = '"><script>'
    html = client.get("/accounts/login/").content.decode()
    assert '<html lang="en">' in html
    assert "data-theme" not in html
    assert '<meta name="color-scheme" content="light dark">' in html


def test_the_account_menu_offers_the_three_choices_with_the_current_one_pressed(client: Client):
    user = UserFactory.create(verified=True)
    client.force_login(user)
    client.cookies[settings.THEME_COOKIE_NAME] = "light"
    html = client.get("/me/").content.decode()
    assert (
        '<form class="theme-choice theme-choice--menu" method="post" action="/accounts/theme/">'
        in html
    )
    assert '<input type="hidden" name="next" value="/me/">' in html
    assert pressed(html) == {"light": "true", "dark": "false", "system": "false"}
    # Each button keeps its word as text (shown in the menu, visually hidden on the sign-in page).
    for word in ("Light", "Dark", "System"):
        assert f'<span class="theme-choice__text">{word}</span></button>' in html


def test_the_sign_in_page_offers_the_choice_too(client: Client):
    """Spec §12 rev 31: signed-out visitors can pick a theme on the auth layout."""
    client.cookies[settings.THEME_COOKIE_NAME] = "dark"
    html = client.get("/accounts/login/?next=/me/").content.decode()
    assert (
        '<form class="theme-choice theme-choice--auth" method="post" action="/accounts/theme/">'
        in html
    )
    assert '<input type="hidden" name="next" value="/accounts/login/?next=/me/">' in html
    assert 'aria-labelledby="theme-choice-auth"' in html
    assert pressed(html) == {"light": "false", "dark": "true", "system": "false"}
    # Spec §12 rev 32: icons with a title for each choice.
    assert 'title="Light theme"' in html and 'title="Dark theme"' in html
    assert '#sun"' in html and '#moon"' in html and '#monitor"' in html
