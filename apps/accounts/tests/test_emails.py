from typing import Any

import pytest
from django.template.loader import get_template
from django.test import RequestFactory

from apps.accounts.adapters import AccountAdapter
from apps.accounts.tests.factories import UserFactory
from apps.workspace.emails import KINDS
from apps.workspace.models import EmailOutbox

ALLAUTH_KINDS = {
    "email_confirmation_signup",
    "email_confirmation",
    "password_reset_key",
    "account_already_exists",
    "password_changed",
    "password_reset",
    "email_changed",
    "email_deleted",
    "password_set",
    "account_connected",
    "account_disconnected",
}


def test_every_allauth_kind_is_registered() -> None:
    assert ALLAUTH_KINDS <= set(KINDS)


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
