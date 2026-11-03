import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, promote_to_office
from apps.accounts.tests.factories import UserFactory
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


def test_promote_to_office_makes_one_primary_verified_address(db):
    user = UserFactory.create(email="ana@scholarsync.test", verified=False)
    EmailAddress.objects.filter(user=user).update(primary=False)
    EmailAddress.objects.create(user=user, email="other@scholarsync.test", primary=True)
    promote_to_office(user=user, full_name="Ana Cruz", password=PASSWORD)
    primary = EmailAddress.objects.get(user=user, primary=True)
    assert primary.email == "ana@scholarsync.test" and primary.verified
    assert user.is_super_admin
    assert AuditEvent.objects.get(action="user.promoted").data == {
        "role": "super_admin",
        "was_verified": False,
    }


def test_promote_to_office_checks_the_password(db):
    user = UserFactory.create(email="ana@scholarsync.test", verified=False)
    with pytest.raises(ValidationError):
        promote_to_office(user=user, full_name="Ana Cruz", password="12345678")
    user.refresh_from_db()
    assert user.is_student
