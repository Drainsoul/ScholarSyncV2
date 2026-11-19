from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.base import AuthProcess
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.base_user import AbstractBaseUser
from django.forms import BaseForm
from django.http import Http404, HttpRequest
from django.shortcuts import redirect

from apps.core.shell import home_url_for
from apps.workspace import emails

from . import mfa_secrets
from .models import User


def _is_privileged(user: object) -> bool:
    """Staff, the scholarship office, or anyone with a Django staff or superuser flag."""
    return isinstance(user, User) and (
        user.role != User.Role.STUDENT or user.is_staff or user.is_superuser
    )


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

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        # allauth applies a safe `next` before it asks the adapter, so this is only the default.
        assert isinstance(request.user, User)
        return home_url_for(request.user)

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
        # The name is typed by whoever signed up, so it only goes to an address its owner has
        # verified. Anyone can register someone else's address with a phishing name.
        user = context.get("user")
        if (
            "full_name" in allowed
            and isinstance(user, User)
            and user.full_name
            and EmailAddress.objects.filter(user=user, email__iexact=email, verified=True).exists()
        ):
            data["full_name"] = user.full_name
        provider_name = getattr(context.get("provider"), "name", "")
        if provider_name and "provider_name" in allowed:
            data["provider_name"] = str(provider_name)
        emails.enqueue(to=email, kind=kind, context=data)


class SocialAccountAdapter(DefaultSocialAccountAdapter):  # type: ignore[misc]
    def get_app(self, request: HttpRequest, provider: str, client_id: str | None = None) -> Any:
        """A provider without credentials answers 404, not a 500 (explore mode has no keys)."""
        try:
            return super().get_app(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist:
            raise Http404 from None

    def pre_social_login(self, request: HttpRequest, sociallogin: Any) -> None:
        """Google sign-in and connecting Google are for students only.

        allauth calls this after both lookups (an existing Google link, then a verified email
        match) and before anything logs in or connects. A staff or scholarship-office account must
        be signed into with its password, so no Google account can ever reach it.
        """
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            if _is_privileged(request.user):
                messages.error(
                    request, "Staff and scholarship-office accounts sign in with their password."
                )
                assert isinstance(request.user, User)
                raise ImmediateHttpResponse(redirect(home_url_for(request.user)))
            return
        if sociallogin.is_existing and _is_privileged(sociallogin.user):
            messages.error(
                request, "This account signs in with its email and password. Sign in below."
            )
            raise ImmediateHttpResponse(redirect("account_login"))

    def save_user(
        self, request: HttpRequest, sociallogin: Any, form: BaseForm | None = None
    ) -> Any:
        _force_student(sociallogin.user)
        user = super().save_user(request, sociallogin, form)
        if (user.role, user.is_staff, user.is_superuser) != (User.Role.STUDENT, False, False):
            _force_student(user)
            user.save()
        return user


class MFAAdapter(DefaultMFAAdapter):  # type: ignore[misc]
    """While 2FA is required, staff and the office can't remove their own authenticator: the
    office removes a lost one (M13). Anyone else may switch theirs off.

    TOTP secrets and recovery-code seeds are encrypted at rest (`mfa_secrets`)."""

    def can_delete_authenticator(self, authenticator: Any) -> bool:
        user = authenticator.user
        required = settings.MFA_REQUIRED_FOR_STAFF and (
            user.is_program_staff or user.is_super_admin
        )
        return not required

    def encrypt(self, text: str) -> str:
        return mfa_secrets.encrypt(text)

    def decrypt(self, encrypted_text: str) -> str:
        return mfa_secrets.decrypt(encrypted_text)
