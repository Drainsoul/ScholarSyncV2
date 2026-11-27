"""The public demo's lockdown (branch `demo`, docs/design/2026-11-28-hosted-demo-design.md 5.2).

The test accounts are shared by every visitor, so nobody may change how they sign in: the
self-service pages that would are refused by the middleware, and the guards refuse the same changes
from anywhere else (an office screen, say). The loader and the nightly reset run inside `bypass()`.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete, pre_save
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.models import User
from apps.demo.accounts import LISTED_EMAILS, PASSWORD

# Every account, 2FA, social and session route is in exactly one set (test_lockdown checks).
FROZEN_URL_NAMES = frozenset(
    {
        "account_change_password",
        "account_set_password",
        "account_reset_password",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_reset_password_from_key_done",
        "account_email",
        "account_signup",
        "socialaccount_signup",
        "socialaccount_connections",
        "google_login",
        "google_callback",
        "mfa_activate_totp",
        "mfa_deactivate_totp",
        "mfa_generate_recovery_codes",
        # Signing out "other sessions" would sign out every other visitor.
        "usersessions_list",
    }
)
ALLOWED_URL_NAMES = frozenset(
    {
        "account_login",
        "account_logout",
        "account_inactive",
        "account_confirm_email",
        "account_email_verification_sent",
        "account_confirm_login_code",
        "account_reauthenticate",
        "account_request_reauthentication_code",
        "account_confirm_reauthentication_code",
        "mfa_authenticate",
        "mfa_reauthenticate",
        "mfa_index",
        "mfa_view_recovery_codes",
        "mfa_download_recovery_codes",
        "socialaccount_login_cancelled",
        "socialaccount_login_error",
        "google_login_by_token",
    }
)

# Office actions that end every session of the account in the URL (`pk`): on a shared test account
# they would sign out every visitor using it. Refused only when that account is a test account.
FROZEN_FOR_DEMO_TARGETS = frozenset({"office:staff-sessions", "office:staff-mfa"})

# Fields that decide who can sign in as a user, and as what.
GUARDED_FIELDS = ("email", "password", "is_active", "role", "is_staff", "is_superuser")

USER_GUARD = "demo-lockdown-user"
EMAIL_GUARD = "demo-lockdown-email"
EMAIL_DELETE_GUARD = "demo-lockdown-email-delete"
AUTHENTICATOR_GUARD = "demo-lockdown-authenticator"

_bypassed: ContextVar[bool] = ContextVar("demo_lockdown_bypassed", default=False)
REFUSED = "The demo's test accounts can't be changed."


@contextmanager
def bypass() -> Iterator[None]:
    """Let the loader and the reset write the test accounts."""
    token = _bypassed.set(True)
    try:
        yield
    finally:
        _bypassed.reset(token)


def _is_demo_email(email: str) -> bool:
    return email.strip().lower() in LISTED_EMAILS


def _targets_demo_account(kwargs: dict[str, Any]) -> bool:
    pk = kwargs.get("pk")
    if not isinstance(pk, int):
        return False
    email = User.objects.filter(pk=pk).values_list("email", flat=True).first()
    return email is not None and _is_demo_email(email)


class PublicDemoLockdownMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self, request: HttpRequest, view_func: object, view_args: object, view_kwargs: object
    ) -> HttpResponse | None:
        match = request.resolver_match
        if not settings.PUBLIC_DEMO or match is None:
            return None
        if match.url_name in FROZEN_URL_NAMES or (
            match.view_name in FROZEN_FOR_DEMO_TARGETS and _targets_demo_account(match.kwargs)
        ):
            return render(request, "demo/frozen.html", status=403)
        return None


def guard_user(sender: type[User], instance: User, **kwargs: Any) -> None:
    if _bypassed.get() or instance._state.adding or instance.pk is None:
        return
    stored = User.objects.filter(pk=instance.pk).values(*GUARDED_FIELDS).first()
    if stored is None or not _is_demo_email(stored["email"]):
        return
    for field in GUARDED_FIELDS:
        if getattr(instance, field) == stored[field]:
            continue
        # Django re-hashes on sign-in when the hasher's settings change: same password, new hash.
        if field == "password" and check_password(PASSWORD, instance.password):
            continue
        raise PermissionDenied(REFUSED)


def guard_email_address(sender: type[EmailAddress], instance: EmailAddress, **kwargs: Any) -> None:
    if _bypassed.get():
        return
    owner = User.objects.filter(pk=instance.user_id).values_list("email", flat=True).first()
    if owner is not None and _is_demo_email(owner):
        raise PermissionDenied(REFUSED)


def guard_authenticator(
    sender: type[Authenticator], instance: Authenticator, **kwargs: Any
) -> None:
    if not _bypassed.get():
        raise PermissionDenied(REFUSED)


def connect_guards() -> None:
    pre_save.connect(guard_user, sender=User, dispatch_uid=USER_GUARD)
    pre_save.connect(guard_email_address, sender=EmailAddress, dispatch_uid=EMAIL_GUARD)
    pre_delete.connect(guard_email_address, sender=EmailAddress, dispatch_uid=EMAIL_DELETE_GUARD)
    pre_save.connect(guard_authenticator, sender=Authenticator, dispatch_uid=AUTHENTICATOR_GUARD)
