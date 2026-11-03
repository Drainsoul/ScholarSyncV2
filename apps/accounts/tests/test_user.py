import pytest
from django.db import IntegrityError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory


def test_email_is_the_login_and_is_normalised(db):
    user = User.objects.create_user(" Ana.Cruz@Example.COM ", "x-pass-2026-long")
    assert user.email == "ana.cruz@example.com"
    assert User.USERNAME_FIELD == "email" and not hasattr(user, "username")


def test_emails_are_unique_ignoring_case(db):
    User.objects.create_user("ana@scholarsync.test", "x-pass-2026-long")
    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="ANA@scholarsync.test")])  # bypasses the manager


def test_new_users_are_students(db):
    assert User.objects.create_user("b@scholarsync.test").role == User.Role.STUDENT


def test_superuser_is_technical_only(db):
    admin = User.objects.create_superuser("root@scholarsync.test", "x-pass-2026-long")
    assert admin.is_superuser and admin.is_staff and admin.role == User.Role.STAFF
    assert not admin.is_super_admin


def test_passwords_use_argon2(db):
    user = User.objects.create_user("c@scholarsync.test", "x-pass-2026-long")
    assert user.password.startswith("argon2")


def test_role_is_constrained(db):
    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="d@scholarsync.test", role="wizard")])


def test_role_properties(db):
    assert UserFactory.create(role=User.Role.STUDENT).is_student
    assert UserFactory.create(role=User.Role.STAFF).is_program_staff
    assert UserFactory.create(role=User.Role.SUPER_ADMIN).is_super_admin


def test_factory_builds_a_usable_user(db):
    user = UserFactory.create()
    assert user.email.endswith("@scholarsync.test")
    assert user.check_password("factory-pass-2026")


def test_save_normalises_the_email(db):
    user = User(email=" Mixed@Case.TEST ")
    user.save()
    user.refresh_from_db()
    assert user.email == "mixed@case.test"


def test_clean_normalises_the_email():
    user = User(email=" Mixed@Case.TEST ")
    user.clean()
    assert user.email == "mixed@case.test"


def test_get_by_natural_key_ignores_case(db):
    user = User(email=" Mixed@Case.TEST ")
    user.save()
    assert User.objects.get_by_natural_key("MIXED@case.test") == user


def test_create_user_requires_an_email(db):
    with pytest.raises(ValueError):
        User.objects.create_user("")


def test_create_user_without_password_is_unusable(db):
    assert not User.objects.create_user("np@scholarsync.test").has_usable_password()
