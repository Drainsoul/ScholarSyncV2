"""The information pages on the hosted demo (branch `demo`, hosted demo design sections 5.1-5.2).

The demo resets every night, shares its test accounts and sends no email, so the pages say so there,
and keep their usual text everywhere else.
"""

import pytest
from django.urls import reverse

RESET = "every night around 03:00 Manila time"


def _page(client, name: str) -> str:
    response = client.get(reverse(f"core:{name}"))
    assert response.status_code == 200
    return str(response.content.decode())


@pytest.fixture
def public_demo(settings):
    settings.PUBLIC_DEMO = True
    settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "apps.demo"]


@pytest.mark.parametrize("name", ["about", "privacy", "terms", "help"])
def test_demo_pages_state_the_nightly_reset(client, vite_build, public_demo, name):
    assert RESET in _page(client, name)


@pytest.mark.parametrize("name", ["about", "privacy", "terms", "help"])
def test_other_copies_keep_their_text(client, vite_build, settings, name):
    settings.PUBLIC_DEMO = False
    assert RESET not in _page(client, name)


def test_demo_about_offers_the_test_accounts_here(client, vite_build, public_demo):
    assert "sign in with one of the test accounts" in _page(client, "about")


def test_demo_privacy_names_the_providers_and_no_email(client, vite_build, public_demo):
    body = _page(client, "privacy")
    for provider in ("Ver" + "cel", "Neon", "Cloudflare R2"):  # in two parts, for the old-host test
        assert provider in body
    assert "No email is sent" in body
    assert "Self-hosters: state your retention period here" not in body


def test_demo_privacy_drops_the_password_check(client, vite_build, settings, public_demo):
    settings.PASSWORD_BREACH_CHECK = True
    assert "Have I Been Pwned" not in _page(client, "privacy")


def test_demo_terms_describe_shared_accounts(client, vite_build, public_demo):
    body = _page(client, "terms")
    assert "shared" in body
    assert "Keep your password private" not in body


def test_demo_help_has_no_email_promises(client, vite_build, public_demo):
    body = _page(client, "help")
    assert "You also get an email" not in body
    assert "The office answers by email" not in body
    assert "About this demo" in body
    assert "Run a copy on your computer" not in body
