from pathlib import Path
from typing import Any

import allauth
import pytest
from django.conf import settings
from django.template.loader import get_template
from django.test import RequestFactory

from apps.accounts.adapters import AccountAdapter
from apps.accounts.tests.factories import UserFactory
from apps.workspace.emails import KINDS
from apps.workspace.models import EmailOutbox

# allauth kinds our settings never send. Anything else allauth ships must be in KINDS, so an
# allauth upgrade that adds a kind fails this test instead of a send_mail at runtime.
DISABLED_ALLAUTH_KINDS = {
    "login_code",  # ACCOUNT_LOGIN_BY_CODE_ENABLED is off
    "password_reset_code",  # password reset is by link, not by code
    "unknown_account",  # ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
    "email_confirm",  # a legacy template; no allauth code path sends it
}
# mfa is not installed, and its templates live under mfa/email/, outside these two folders.
ALLAUTH_TEMPLATES = Path(allauth.__file__).parent / "templates"


def _installed_allauth_kinds() -> set[str]:
    return {
        path.name.removesuffix("_subject.txt")
        for folder in ("account", "socialaccount")
        for path in (ALLAUTH_TEMPLATES / folder / "email").glob("*_subject.txt")
    }


def test_every_allauth_kind_is_registered() -> None:
    expected = _installed_allauth_kinds() - DISABLED_ALLAUTH_KINDS
    assert DISABLED_ALLAUTH_KINDS <= _installed_allauth_kinds()  # the list is not stale
    assert {kind for kind in KINDS if kind in _installed_allauth_kinds()} == expected


def test_the_disabled_allauth_kinds_stay_disabled() -> None:
    from allauth.account import app_settings

    assert not app_settings.LOGIN_BY_CODE_ENABLED
    assert not app_settings.PASSWORD_RESET_BY_CODE_ENABLED
    assert not app_settings.EMAIL_UNKNOWN_ACCOUNTS


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_allauth_kind_has_three_templates(kind: str) -> None:
    for name in (f"{kind}_subject.txt", f"{kind}.txt", f"{kind}.html"):
        get_template(f"emails/{name}")


def test_adapter_keeps_only_whitelisted_strings(db: Any, rf: RequestFactory) -> None:
    user = UserFactory.create(full_name="Ana Cruz")
    AccountAdapter().send_mail(
        "account/email/password_reset_key",
        user.email,
        {
            "user": user,
            "key": "k",
            "request": rf.get("/"),
            "password_reset_url": "https://x.test/a/",
        },
    )
    row = EmailOutbox.objects.get()
    assert row.context == {"password_reset_url": "https://x.test/a/", "full_name": "Ana Cruz"}


def test_unverified_address_mails_carry_no_name(db: Any) -> None:
    user = UserFactory.create(full_name="Visit https://evil.example now")
    for prefix in ("email_confirmation_signup", "email_confirmation"):
        AccountAdapter().send_mail(
            f"account/email/{prefix}", user.email, {"user": user, "activate_url": "https://x.test/"}
        )
    assert all(
        row.context == {"activate_url": "https://x.test/"} for row in EmailOutbox.objects.all()
    )


EVIL = "Visit https://evil.example now"


def test_reset_to_an_unverified_address_carries_no_name(
    db: Any, rf: RequestFactory, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    user = UserFactory.create(full_name=EVIL, verified=False)
    with django_capture_on_commit_callbacks(execute=True):
        AccountAdapter().send_mail(
            "account/email/password_reset_key",
            user.email,
            {"user": user, "password_reset_url": "https://x.test/r/"},
        )
    assert EmailOutbox.objects.get().context == {}  # sent rows forget their context
    assert "evil.example" not in mailoutbox[0].body
    assert "evil.example" not in str(mailoutbox[0].alternatives)


def test_reset_row_context_to_an_unverified_address_has_no_name(db: Any) -> None:
    user = UserFactory.create(full_name=EVIL, verified=False)
    AccountAdapter().send_mail(
        "account/email/password_reset_key",
        user.email,
        {"user": user, "password_reset_url": "https://x.test/r/"},
    )
    assert EmailOutbox.objects.get().context == {"password_reset_url": "https://x.test/r/"}


def test_reset_to_a_verified_address_includes_the_name(db: Any) -> None:
    user = UserFactory.create(full_name="Ana Cruz", verified=True)
    AccountAdapter().send_mail(
        "account/email/password_reset_key",
        user.email.upper(),
        {"user": user, "password_reset_url": "https://x.test/r/"},
    )
    assert EmailOutbox.objects.get().context["full_name"] == "Ana Cruz"


def test_account_exists_to_an_unverified_address_carries_no_name(db: Any) -> None:
    user = UserFactory.create(full_name=EVIL, verified=False)
    AccountAdapter().send_mail(
        "account/email/account_already_exists",
        user.email,
        {
            "user": user,
            "signup_url": "https://x.test/s/",
            "password_reset_url": "https://x.test/r/",
        },
    )
    assert "full_name" not in EmailOutbox.objects.get().context


def test_text_bodies_are_not_html_escaped(
    db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    user = UserFactory.create(full_name="Ana D'Souza & <Co>", verified=True)
    with django_capture_on_commit_callbacks(execute=True):
        AccountAdapter().send_mail("account/email/password_changed", user.email, {"user": user})
    message = mailoutbox[0]
    assert "Hello Ana D'Souza & <Co>," in message.body
    assert "D&#x27;Souza &amp; &lt;Co&gt;" in message.alternatives[0][0]  # HTML stays escaped


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_text_body_extends_the_unescaped_base(kind: str) -> None:
    source = (settings.BASE_DIR / "templates" / "emails" / f"{kind}.txt").read_text("utf-8")
    assert source.startswith('{% extends "emails/base.txt" %}')
