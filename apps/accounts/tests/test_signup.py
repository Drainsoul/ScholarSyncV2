from smtplib import SMTPException
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.test import RequestFactory

from apps.accounts.adapters import SocialAccountAdapter
from apps.accounts.forms import SocialSignupForm
from apps.accounts.models import ConsentRecord, User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.workspace.models import EmailOutbox

SIGNUP = {
    "full_name": "Ana Cruz",
    "email": " Ana.Cruz@Scholarsync.TEST ",
    "password1": "signup-pass-2026",
    "password2": "signup-pass-2026",
    "consent": "on",
}


def test_signup_creates_an_unverified_student_and_queues_the_email(
    client: Any, db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/accounts/signup/", SIGNUP)
    assert response.status_code == 302
    assert response.url == "/accounts/confirm-email/"
    user = User.objects.get()
    assert user.email == "ana.cruz@scholarsync.test"
    assert user.role == User.Role.STUDENT and user.full_name == "Ana Cruz"
    assert not EmailAddress.objects.filter(user=user, verified=True).exists()
    row = EmailOutbox.objects.get()
    assert row.kind == "email_confirmation_signup" and row.status == "sent"
    assert "/accounts/confirm-email/" in mailoutbox[0].body
    assert ConsentRecord.objects.get(user=user).notice_version == settings.PRIVACY_NOTICE_VERSION
    actions = set(AuditEvent.objects.filter(actor=user).values_list("action", flat=True))
    assert {"user.signed_up", "consent.recorded"} <= actions
    assert "ana.cruz" not in str(list(AuditEvent.objects.values_list("data", flat=True))).lower()


def test_signup_ignores_role_and_staff_fields(client: Any, db: Any) -> None:
    client.post(
        "/accounts/signup/",
        SIGNUP | {"role": "super_admin", "is_staff": "on", "is_superuser": "on"},
    )
    user = User.objects.get()
    assert user.role == User.Role.STUDENT
    assert not user.is_staff and not user.is_superuser


def test_signup_needs_consent(client: Any, db: Any) -> None:
    data = {k: v for k, v in SIGNUP.items() if k != "consent"}
    response = client.post("/accounts/signup/", data)
    assert response.status_code == 200
    assert response.context["form"].errors.get("consent")
    assert User.objects.count() == 0 and ConsentRecord.objects.count() == 0


def test_signup_with_an_existing_email_in_other_case_sends_account_exists(
    client: Any, db: Any, django_capture_on_commit_callbacks: Any
) -> None:
    UserFactory.create(email="ana.cruz@scholarsync.test", verified=True)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/accounts/signup/", SIGNUP | {"email": "ANA.CRUZ@scholarsync.test"})
    assert response.status_code == 302 and response.url == "/accounts/confirm-email/"
    assert User.objects.count() == 1
    assert EmailOutbox.objects.get().kind == "account_already_exists"


def test_signup_survives_smtp_down(
    client: Any, db: Any, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: Any
) -> None:
    def boom(self: Any, *args: Any, **kwargs: Any) -> int:
        raise SMTPException("down")

    monkeypatch.setattr(EmailMultiAlternatives, "send", boom)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/accounts/signup/", SIGNUP)
    assert response.status_code == 302
    assert User.objects.count() == 1
    assert EmailOutbox.objects.get().status == "failed"


def test_google_signup_form_asks_for_consent() -> None:
    assert SocialSignupForm.base_fields["consent"].required


def test_social_adapter_forces_student(db: Any, rf: RequestFactory) -> None:
    request = rf.get("/")
    request.session = {}  # type: ignore[assignment]
    user = User(
        email="g@scholarsync.test", role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True
    )

    class FakeForm:
        cleaned_data = {
            "email": "g@scholarsync.test",
            "full_name": "Gina Reyes",
            "role": "super_admin",
        }

    saved = SocialAccountAdapter().save_user(
        request,
        SocialLogin(user=user, account=SocialAccount(provider="google", uid="g-1")),
        form=FakeForm(),  # type: ignore[arg-type]
    )
    saved.refresh_from_db()
    assert saved.role == User.Role.STUDENT
    assert not saved.is_staff and not saved.is_superuser
