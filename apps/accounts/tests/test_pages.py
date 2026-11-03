import re
from typing import Any

import pytest

URLS = ["/accounts/login/", "/accounts/signup/", "/accounts/password/reset/"]
GOOGLE = {
    "google": {
        "APPS": [{"client_id": "id.apps.example", "secret": "s3cret"}],
        "SCOPE": ["profile", "email"],
    }
}


def _get(client: Any, url: str) -> str:
    response = client.get(url)
    assert response.status_code == 200
    return str(response.content.decode())


@pytest.mark.parametrize("url", URLS)
def test_account_pages_use_the_auth_layout(client: Any, vite_build: Any, db: Any, url: str) -> None:
    body = _get(client, url)
    assert 'class="auth"' in body
    assert body.count("<h1") == 1


@pytest.mark.parametrize(
    ("url", "heading"),
    [
        ("/accounts/login/", "Log in"),
        ("/accounts/signup/", "Create your account"),
        ("/accounts/password/reset/", "Reset your password"),
    ],
)
def test_headings_and_main_buttons(
    client: Any, vite_build: Any, db: Any, url: str, heading: str
) -> None:
    body = _get(client, url)
    assert f"<h1>{heading}</h1>" in body
    assert 'class="btn btn--primary"' in body


@pytest.mark.parametrize("url", [*URLS, "/accounts/confirm-email/"])
def test_every_input_has_a_label(client: Any, vite_build: Any, db: Any, url: str) -> None:
    body = _get(client, url)
    ids = re.findall(r'<input(?![^>]*type="hidden")[^>]*\bid="([^"]+)"', body)
    for input_id in ids:
        assert f'for="{input_id}"' in body, input_id


def test_signup_inputs_are_labelled_as_the_e2e_flow_expects(
    client: Any, vite_build: Any, db: Any
) -> None:
    body = _get(client, "/accounts/signup/")
    for label in ("Full name", "Email", "Password", "Password (again)"):
        assert re.search(rf"<label[^>]*>\s*{re.escape(label)}\s*<", body), label
    assert "I have read the privacy notice" in body


def test_login_links_to_signup_and_reset(client: Any, vite_build: Any, db: Any) -> None:
    body = _get(client, "/accounts/login/")
    assert 'id="login-form"' in body
    assert 'name="login"' in body and 'name="password"' in body
    assert 'href="/accounts/signup/"' in body and "Create an account" in body
    assert 'href="/accounts/password/reset/"' in body and "Forgot your password?" in body


def test_signup_links_to_login(client: Any, vite_build: Any, db: Any) -> None:
    body = _get(client, "/accounts/signup/")
    assert "Already have an account?" in body and 'href="/accounts/login/"' in body


def test_google_button_only_when_configured(
    client: Any, vite_build: Any, db: Any, settings: Any
) -> None:
    settings.SOCIALACCOUNT_PROVIDERS = {}
    assert "Continue with Google" not in _get(client, "/accounts/login/")
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    body = _get(client, "/accounts/login/")
    assert "Continue with Google" in body
    assert "Continue with Google" in _get(client, "/accounts/signup/")


def test_signup_consent_links_the_privacy_notice(client: Any, vite_build: Any, db: Any) -> None:
    body = _get(client, "/accounts/signup/")
    start = body.index('type="checkbox"')
    assert 'href="/privacy/"' in body[start : start + 600]


def test_verification_sent_page(client: Any, vite_build: Any, db: Any) -> None:
    body = _get(client, "/accounts/confirm-email/")
    assert "<h1>Check your email</h1>" in body
    assert "We sent a link to confirm your address. It expires in 3 days." in body


def test_form_errors_form_an_alert_that_takes_focus(client: Any, vite_build: Any, db: Any) -> None:
    response = client.post("/accounts/login/", {"login": "x@scholarsync.test", "password": "nope"})
    body = response.content.decode()
    assert 'role="alert"' in body and 'tabindex="-1"' in body and "autofocus" in body


@pytest.mark.parametrize(
    "url",
    ["/accounts/email/", "/accounts/password/change/", "/accounts/logout/"],
)
def test_signed_in_account_pages_render_with_submit_buttons(
    client: Any, vite_build: Any, db: Any, url: str
) -> None:
    from apps.accounts.tests.factories import UserFactory

    client.force_login(UserFactory.create(verified=True))
    body = _get(client, url)
    buttons = re.findall(r"<button\b[^>]*>", body)
    assert buttons
    for tag in buttons:
        if "data-" in tag or "icon-btn" in tag or 'aria-label="Dismiss"' in tag:
            continue  # the site's own chrome (toasts, menus), not allauth's
        assert "type=" not in tag or 'type="submit"' in tag or 'type="button"' in tag
    action = [t for t in buttons if 'class="btn' in t]
    assert action and all('type="button"' not in t for t in action)
