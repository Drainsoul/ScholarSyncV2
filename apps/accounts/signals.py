from typing import Any

from allauth.account.signals import email_confirmed, password_changed, password_reset
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
