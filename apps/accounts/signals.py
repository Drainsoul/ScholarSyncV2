from typing import Any

from allauth.account.signals import email_confirmed, password_changed, password_reset, password_set
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
    record(actor=user, action="user.signed_in", target=user, request=request)


@receiver(user_logged_out)
def on_signed_out(request: HttpRequest | None, user: User | None, **kwargs: Any) -> None:
    if user is not None:
        record(actor=user, action="user.signed_out", target=user, request=request)


@receiver(user_login_failed)
def on_sign_in_failed(request: HttpRequest | None = None, **kwargs: Any) -> None:
    record(actor=None, action="user.sign_in_failed", request=request)
