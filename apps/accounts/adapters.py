from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth.base_user import AbstractBaseUser
from django.forms import BaseForm
from django.http import HttpRequest
from django.shortcuts import redirect

from apps.workspace import emails

from .models import User


def _force_student(user: User) -> None:
    user.role = User.Role.STUDENT
    user.is_staff = False
    user.is_superuser = False


class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]
    def save_user(
        self, request: HttpRequest, user: AbstractBaseUser, form: BaseForm, commit: bool = True
    ) -> AbstractBaseUser:
        saved = super().save_user(request, user, form, commit=False)
        assert isinstance(saved, User)
        saved.full_name = str(form.cleaned_data.get("full_name", "")).strip()
        _force_student(saved)
        if commit:
            saved.save()
        return saved

    def send_notification_mail(
        self,
        template_prefix: str,
        user: AbstractBaseUser,
        context: dict[str, Any] | None = None,
        email: str | None = None,
    ) -> None:
        # allauth leaves the user out of notification contexts; the greeting needs the name.
        super().send_notification_mail(
            template_prefix, user, {"user": user, **(context or {})}, email
        )

    def send_mail(self, template_prefix: str, email: str, context: dict[str, Any]) -> None:
        """Queue the message in the outbox instead of sending it inline."""
        kind = template_prefix.rsplit("/", 1)[-1]
        allowed = emails.KINDS[kind]
        data = {
            key: str(value)
            for key, value in context.items()
            if key in allowed and key not in ("full_name", "provider_name")
        }
        full_name = getattr(context.get("user"), "full_name", "")
        if full_name and "full_name" in allowed:
            data["full_name"] = str(full_name)
        provider_name = getattr(context.get("provider"), "name", "")
        if provider_name and "provider_name" in allowed:
            data["provider_name"] = str(provider_name)
        emails.enqueue(to=email, kind=kind, context=data)


class SocialAccountAdapter(DefaultSocialAccountAdapter):  # type: ignore[misc]
    def authenticate_by_email(self, sociallogin: Any) -> Any:
        """Email sign-in and auto-connect are for students only.

        A staff or scholarship-office account must be signed into with its password, so a Google
        account that merely shares its email address can never reach it.
        """
        found = super().authenticate_by_email(sociallogin)
        if found is None or sociallogin.state.get("process") == "connect":
            return found
        user = found[0]
        if user.role != User.Role.STUDENT or user.is_staff or user.is_superuser:
            messages.error(
                context.request,
                "This account signs in with its email and password. Sign in below.",
            )
            raise ImmediateHttpResponse(redirect("account_login"))
        return found

    def save_user(
        self, request: HttpRequest, sociallogin: Any, form: BaseForm | None = None
    ) -> Any:
        _force_student(sociallogin.user)
        user = super().save_user(request, sociallogin, form)
        if (user.role, user.is_staff, user.is_superuser) != (User.Role.STUDENT, False, False):
            _force_student(user)
            user.save()
        return user
