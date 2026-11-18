import time
from typing import Any

from allauth.account.signals import email_confirmed, password_changed, password_reset, password_set
from allauth.mfa.signals import authenticator_added, authenticator_removed, authenticator_reset
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

from apps.core.audit import record

from .models import User


@receiver(email_confirmed)
def on_email_confirmed(request: HttpRequest | None, email_address: Any, **kwargs: Any) -> None:
    record(
        actor=email_address.user,
        action="user.email_confirmed",
        target=email_address.user,
        request=request,
    )


@receiver(password_reset)
def on_password_reset(request: HttpRequest | None, user: User, **kwargs: Any) -> None:
    record(actor=user, action="user.password_reset", target=user, request=request)


@receiver(password_changed)
def on_password_changed(request: HttpRequest | None, user: User, **kwargs: Any) -> None:
    record(actor=user, action="user.password_changed", target=user, request=request)


@receiver(password_set)
def on_password_set(request: HttpRequest | None, user: User, **kwargs: Any) -> None:
    record(actor=user, action="user.password_set", target=user, request=request)


# Sign-ins (spec §10, M12). A failed sign-in has no actor and no data: the typed email is never
# stored, so a mistyped password can't leave someone's address in the audit log.
@receiver(user_logged_in)
def on_signed_in(request: HttpRequest | None, user: User, **kwargs: Any) -> None:
    if request is not None and hasattr(request, "session"):
        # Session limits count from here (apps/accounts/session_policy.py).
        now = time.time()
        request.session["signed_in_at"] = now
        request.session["last_seen"] = now
    record(actor=user, action="user.signed_in", target=user, request=request)


@receiver(user_logged_out)
def on_signed_out(request: HttpRequest | None, user: User | None, **kwargs: Any) -> None:
    if user is not None:
        record(actor=user, action="user.signed_out", target=user, request=request)


@receiver(user_login_failed)
def on_sign_in_failed(request: HttpRequest | None = None, **kwargs: Any) -> None:
    record(actor=None, action="user.sign_in_failed", request=request)


# One's own two-factor changes (M13). Only the kind of authenticator is recorded.
@receiver(authenticator_added)
def on_authenticator_added(
    request: HttpRequest | None, user: User, authenticator: Any, **kwargs: Any
) -> None:
    record(
        actor=user,
        action="mfa.added",
        target=user,
        data={"type": authenticator.type},
        request=request,
    )


@receiver(authenticator_removed)
def on_authenticator_removed(
    request: HttpRequest | None, user: User, authenticator: Any, **kwargs: Any
) -> None:
    if request is not None and hasattr(request, "session"):
        # The 2FA requirement cached "has an authenticator" in the session: check again.
        from .mfa_policy import SESSION_KEY

        request.session.pop(SESSION_KEY, None)
    record(
        actor=user,
        action="mfa.deactivated",
        target=user,
        data={"type": authenticator.type},
        request=request,
    )


@receiver(authenticator_reset)
def on_authenticator_reset(
    request: HttpRequest | None, user: User, authenticator: Any, **kwargs: Any
) -> None:
    record(
        actor=user,
        action="mfa.reset",
        target=user,
        data={"type": authenticator.type},
        request=request,
    )
