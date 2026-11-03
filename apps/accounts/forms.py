from typing import Any

from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest
from django.utils.html import format_html

from apps.core.audit import record

from .models import User
from .services import record_consent


class ConsentFieldsMixin(forms.Form):
    """The two fields every sign-up asks for, and what is recorded once the account exists."""

    field_order = ["email", "full_name", "password1", "password2", "consent"]

    full_name = forms.CharField(label="Full name", max_length=150, strip=True)
    consent = forms.BooleanField(
        label="I have read the privacy notice",
        help_text=format_html('<a href="{}">Read the privacy notice</a>', "/privacy/"),
        required=True,
    )

    def _record_signup(self, request: HttpRequest, user: AbstractBaseUser) -> None:
        assert isinstance(user, User)
        record(actor=user, action="user.signed_up", target=user, request=request)
        record_consent(user=user, request=request)


class SignupForm(ConsentFieldsMixin, AllauthSignupForm):  # type: ignore[misc]
    def save(self, request: HttpRequest) -> AbstractBaseUser:
        # One transaction: the account, its verification row, the consent and the audit trail.
        with transaction.atomic():
            user: AbstractBaseUser = super().save(request)
            self._record_signup(request, user)
        return user


class SocialSignupForm(ConsentFieldsMixin, AllauthSocialSignupForm):  # type: ignore[misc]
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("full_name"):
            self.initial["full_name"] = self.sociallogin.user.full_name

    def save(self, request: HttpRequest) -> AbstractBaseUser:
        with transaction.atomic():
            user: AbstractBaseUser = super().save(request)
            self._record_signup(request, user)
        return user
