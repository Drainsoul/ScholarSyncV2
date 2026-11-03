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
        "account/email/email_confirmation_signup",
        user.email,
        {"user": user, "key": "k", "request": rf.get("/"), "activate_url": "https://x.test/a/"},
    )
    row = EmailOutbox.objects.get()
    assert row.context == {"activate_url": "https://x.test/a/", "full_name": "Ana Cruz"}
