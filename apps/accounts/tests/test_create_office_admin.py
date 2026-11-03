import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory

EMAIL = "Office@Scholarsync.test"


def test_creates_a_verified_office_account(db, monkeypatch, capsys):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana Cruz", "--no-input")
    user = User.objects.get(email="office@scholarsync.test")
    assert user.is_super_admin and user.check_password("office-pass-2026")
    out = capsys.readouterr().out
    assert "Office account created. Log in at /accounts/login/." in out
    assert "scholarsync.test" not in out.lower()


def test_refuses_an_existing_email(db, monkeypatch):
    monkeypatch.setenv("OFFICE_ADMIN_PASSWORD", "office-pass-2026")
    UserFactory.create(email="office@scholarsync.test")
    with pytest.raises(CommandError) as exc:
        call_command("create_office_admin", "--email", EMAIL, "--full-name", "Ana", "--no-input")
    assert "--email" in str(exc.value)
    assert "scholarsync.test" not in str(exc.value).lower()


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
