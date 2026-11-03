import pytest
from allauth.account.models import EmailAddress, EmailConfirmation
from allauth.socialaccount.models import SocialAccount
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, promote_to_office
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.models import AuditEvent

PASSWORD = "a-long-office-pass-2026"


def test_office_can_create_staff(db):
    actor = UserFactory.create(role=User.Role.SUPER_ADMIN)
    user = create_staff_user(
        actor=actor,
        email="New.Staff@Scholarsync.test",
        full_name="Ana Cruz",
        role=User.Role.STAFF,
        password=PASSWORD,
    )
    assert user.email == "new.staff@scholarsync.test"
    assert user.role == User.Role.STAFF
    address = EmailAddress.objects.get(user=user)
    assert address.verified and address.primary
    event = AuditEvent.objects.get(action="user.created")
    assert event.actor == actor
    assert event.target_id == str(user.pk)
    assert event.data == {"role": "staff"}


def test_command_line_may_create_staff(db):
    user = create_staff_user(
        actor=None,
        email="a@scholarsync.test",
        full_name="A B",
        role=User.Role.SUPER_ADMIN,
        password=PASSWORD,
    )
    assert user.is_super_admin
    assert AuditEvent.objects.get(action="user.created").actor is None


def test_staff_cannot_create_staff(db):
    actor = UserFactory.create(role=User.Role.STAFF)
    with pytest.raises(PermissionDenied):
        create_staff_user(
            actor=actor,
            email="x@scholarsync.test",
            full_name="X",
            role=User.Role.STAFF,
            password=PASSWORD,
        )
    assert not User.objects.filter(email="x@scholarsync.test").exists()


def test_create_staff_user_refuses_the_student_role(db):
    with pytest.raises(ValueError):
        create_staff_user(
            actor=None,
            email="x@scholarsync.test",
            full_name="X",
            role=User.Role.STUDENT,
            password=PASSWORD,
        )


def test_create_staff_user_checks_the_password(db):
    with pytest.raises(ValidationError):
        create_staff_user(
            actor=None,
            email="x@scholarsync.test",
            full_name="X",
            role=User.Role.STAFF,
            password="12345678",
        )
    assert not User.objects.filter(email="x@scholarsync.test").exists()


def test_create_staff_user_without_a_password_has_an_unusable_one(db):
    user = create_staff_user(
        actor=None, email="x@scholarsync.test", full_name="X", role=User.Role.STAFF
    )
    assert not user.has_usable_password()


def test_inactive_super_admin_cannot_create_staff(db):
    actor = UserFactory.create(role=User.Role.SUPER_ADMIN, is_active=False)
    with pytest.raises(PermissionDenied):
        create_staff_user(
            actor=actor,
            email="x@scholarsync.test",
            full_name="X",
            role=User.Role.STAFF,
            password=PASSWORD,
        )
    assert not User.objects.filter(email="x@scholarsync.test").exists()


def test_promote_to_office_removes_every_way_back_in(client, db):
    """A squatter who signed up with the operator's address keeps nothing."""
    user = UserFactory.create(email="ana@scholarsync.test", verified=False)
    EmailAddress.objects.filter(user=user).update(primary=False)
    EmailAddress.objects.create(
        user=user, email="squatter@scholarsync.test", verified=True, primary=True
    )
    SocialAccount.objects.create(user=user, provider="google", uid="g-squat")
    pending = EmailConfirmation.create(EmailAddress.objects.get(email="ana@scholarsync.test"))
    client.post(
        "/accounts/login/", {"login": "squatter@scholarsync.test", "password": DEFAULT_PASSWORD}
    )
    assert client.session["_auth_user_id"] == str(user.pk)
    other = Client()
    other.force_login(UserFactory.create())  # someone else's session survives

    promote_to_office(user=user, full_name="Ana Cruz", password=PASSWORD)

    assert list(
        EmailAddress.objects.filter(user=user).values_list("email", "verified", "primary")
    ) == [("ana@scholarsync.test", True, True)]
    assert not SocialAccount.objects.filter(user=user).exists()
    assert not EmailConfirmation.objects.filter(pk=pending.pk).exists()
    assert Session.objects.count() == 1
    assert AuditEvent.objects.get(action="user.promoted").data == {
        "role": "super_admin",
        "was_verified": False,
        "emails_removed": 1,
        "social_removed": 1,
        "sessions_ended": 1,
    }
    assert "_auth_user_id" not in client.session
    for password in (DEFAULT_PASSWORD, PASSWORD):
        client.post(
            "/accounts/login/", {"login": "squatter@scholarsync.test", "password": password}
        )
        assert "_auth_user_id" not in client.session
    client.post("/accounts/login/", {"login": "ana@scholarsync.test", "password": PASSWORD})
    assert client.session["_auth_user_id"] == str(user.pk)


def test_promote_to_office_checks_the_password(db):
    user = UserFactory.create(email="ana@scholarsync.test", verified=False)
    with pytest.raises(ValidationError):
        promote_to_office(user=user, full_name="Ana Cruz", password="12345678")
    user.refresh_from_db()
    assert user.is_student


def test_promote_to_office_ends_a_half_finished_login(client, db):
    # Signing in to an unverified account stops at "confirm your email" and keeps the login in
    # the session, ready to finish when the confirmation link is opened.
    user = UserFactory.create(email="ana@scholarsync.test", verified=False)
    client.post("/accounts/login/", {"login": "ana@scholarsync.test", "password": DEFAULT_PASSWORD})
    assert "account_login" in client.session
    promote_to_office(user=user, full_name="Ana Cruz", password=PASSWORD)
    assert not Session.objects.exists()
    assert AuditEvent.objects.get(action="user.promoted").data["sessions_ended"] == 1
