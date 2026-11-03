import pytest
from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent

EMAIL = "Office@Scholarsync.test"


def test_creates_a_verified_office_account(db, monkeypatch, capsys):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana Cruz", "--no-input")
    user = User.objects.get(email="office@scholarsync.test")
    assert user.is_super_admin and user.check_password("office-pass-2026")
    out = capsys.readouterr().out
    assert "Office account created. Log in at /accounts/login/." in out
    assert "scholarsync.test" not in out.lower()


def test_refuses_an_existing_verified_address_without_the_flag(db, monkeypatch):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    user = UserFactory.create(email="office@scholarsync.test", verified=True)
    with pytest.raises(CommandError) as exc:
        call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana", "--no-input")
    assert "--promote-existing" in str(exc.value)
    assert "scholarsync.test" not in str(exc.value).lower()
    user.refresh_from_db()
    assert user.is_student and not AuditEvent.objects.filter(action="user.promoted").exists()


def _assert_promoted(user, *, was_verified, out):
    user.refresh_from_db()
    assert user.is_super_admin and user.full_name == "Ana Cruz"
    assert user.check_password("office-pass-2026")
    address = EmailAddress.objects.get(user=user, email="office@scholarsync.test")
    assert address.verified and address.primary
    event = AuditEvent.objects.get(action="user.promoted")
    assert event.actor is None and event.target_id == str(user.pk)
    assert event.data == {"role": "super_admin", "was_verified": was_verified}
    assert "now the office account" in out
    assert "scholarsync.test" not in out.lower()


def test_takes_over_a_never_verified_signup(db, monkeypatch, capsys):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    squatted = UserFactory.create(
        email="office@scholarsync.test", full_name="Visit evil.example", verified=False
    )
    call_command("create_office_admin", "--email", EMAIL, "--full-name", " Ana Cruz ", "--no-input")
    _assert_promoted(squatted, was_verified=False, out=capsys.readouterr().out)
    assert User.objects.count() == 1


def test_promotes_a_verified_account_with_the_flag(db, monkeypatch, capsys):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    user = UserFactory.create(email="office@scholarsync.test", verified=True)
    call_command(
        "create_office_admin",
        "--email",
        EMAIL,
        "--full-name",
        "Ana Cruz",
        "--no-input",
        "--promote-existing",
    )
    _assert_promoted(user, was_verified=True, out=capsys.readouterr().out)


def test_a_weak_password_leaves_the_existing_account_unchanged(db, monkeypatch):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "12345678")
    user = UserFactory.create(email="office@scholarsync.test", verified=False)
    with pytest.raises(CommandError) as exc:
        call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana", "--no-input")
    assert "scholarsync.test" not in str(exc.value).lower()
    user.refresh_from_db()
    assert user.is_student
    assert not EmailAddress.objects.get(user=user).verified
    assert not AuditEvent.objects.filter(action="user.promoted").exists()


def test_no_input_needs_the_password_variable(db, monkeypatch):
    monkeypatch.delenv("OFFICE_ADMIN_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="OFFICE_ADMIN_PASSWORD"):
        call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana", "--no-input")
    assert not User.objects.exists()


def test_a_weak_password_is_refused_without_echoing_the_email(db, monkeypatch):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "12345678")
    with pytest.raises(CommandError) as exc:
        call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana", "--no-input")
    assert "scholarsync.test" not in str(exc.value).lower()
    assert not User.objects.exists()
