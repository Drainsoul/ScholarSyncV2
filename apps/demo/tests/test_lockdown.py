"""The public demo's lockdown (branch `demo`, docs/design/2026-11-28-hosted-demo-design.md 5.2)."""

from collections.abc import Iterator
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete, pre_save
from django.urls import get_resolver, reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.tests.auth import reauthenticated
from apps.demo import lockdown
from apps.demo.accounts import ACCOUNTS, PASSWORD

pytestmark = pytest.mark.django_db

LOCKDOWN = "apps.demo.lockdown.PublicDemoLockdownMiddleware"
PREFIXES = ("account_", "mfa_", "socialaccount_", "usersessions_", "google_")
FROZEN_HEADING = "Not available in the demo"


@pytest.fixture
def public_demo(settings: Any) -> None:
    settings.PUBLIC_DEMO = True
    settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "apps.demo"]
    mfa = settings.MIDDLEWARE.index("apps.accounts.mfa_policy.RequireStaffMfaMiddleware")
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE[: mfa + 1],
        LOCKDOWN,
        *settings.MIDDLEWARE[mfa + 1 :],
    ]


@pytest.fixture
def guards() -> Iterator[None]:
    """Connect the guards as `DemoConfig.ready()` does in the public demo."""
    lockdown.connect_guards()
    yield
    pre_save.disconnect(dispatch_uid=lockdown.USER_GUARD, sender=User)
    pre_save.disconnect(dispatch_uid=lockdown.EMAIL_GUARD, sender=EmailAddress)
    pre_delete.disconnect(dispatch_uid=lockdown.EMAIL_DELETE_GUARD, sender=EmailAddress)
    pre_save.disconnect(dispatch_uid=lockdown.AUTHENTICATOR_GUARD, sender=Authenticator)


def _demo_account(account: Any) -> User:
    with lockdown.bypass():
        return UserFactory.create(
            email=account.email, password=PASSWORD, verified=True, role=account.role
        )


def _demo_user(**extra: Any) -> User:
    account = ACCOUNTS[0]
    with lockdown.bypass():
        return UserFactory.create(
            email=account.email, password=PASSWORD, verified=True, role=account.role, **extra
        )


def test_every_account_route_is_classified() -> None:
    names = {
        name
        for name in get_resolver().reverse_dict
        if isinstance(name, str) and name.startswith(PREFIXES)
    }
    assert not lockdown.FROZEN_URL_NAMES & lockdown.ALLOWED_URL_NAMES
    unclassified = names - lockdown.FROZEN_URL_NAMES - lockdown.ALLOWED_URL_NAMES
    assert not unclassified, sorted(unclassified)


@pytest.mark.parametrize(
    "name", ["account_change_password", "account_email", "account_signup", "mfa_activate_totp"]
)
def test_frozen_route_returns_403_on_post(client: Any, public_demo: None, name: str) -> None:
    user = UserFactory.create(verified=True)
    if name != "account_signup":
        reauthenticated(client, user)
    data = {
        "oldpassword": DEFAULT_PASSWORD,
        "password1": "x-new-pass-2026",
        "password2": "x-new-pass-2026",
    }
    response = client.post(reverse(name), data)
    assert response.status_code == 403
    assert FROZEN_HEADING in response.content.decode()
    user.refresh_from_db()
    assert user.check_password(DEFAULT_PASSWORD)


def test_allowed_route_untouched(client: Any, public_demo: None) -> None:
    response = client.get(reverse("account_login"))
    assert response.status_code == 200
    assert FROZEN_HEADING not in response.content.decode()


def test_middleware_inert_when_flag_off(client: Any, public_demo: None, settings: Any) -> None:
    settings.PUBLIC_DEMO = False
    reauthenticated(client, UserFactory.create(verified=True))
    assert client.get(reverse("account_change_password")).status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "someone.else@scholarsync.test"),
        ("is_active", False),
        ("role", User.Role.SUPER_ADMIN),
    ],
)
def test_guard_refuses_demo_field_change(guards: None, field: str, value: Any) -> None:
    user = _demo_user()
    setattr(user, field, value)
    with pytest.raises(PermissionDenied):
        user.save()


def test_guard_refuses_demo_password_change(guards: None) -> None:
    user = _demo_user()
    user.set_password("a-different-pass-2026")
    with pytest.raises(PermissionDenied):
        user.save()


def test_guard_allows_rehash_of_the_published_password(guards: None) -> None:
    user = _demo_user()
    user.set_password(PASSWORD)
    user.save()


def test_guard_allows_non_demo_users_and_new_rows(guards: None) -> None:
    other = UserFactory.create()
    other.email = "changed@scholarsync.test"
    other.save()
    account = ACCOUNTS[1]
    User.objects.create_user(email=account.email, password=PASSWORD, role=account.role)


def test_guard_allows_bypass(guards: None) -> None:
    user = _demo_user()
    with lockdown.bypass():
        user.set_password("a-different-pass-2026")
        user.save()


def test_guard_refuses_demo_email_address_changes(guards: None) -> None:
    user = _demo_user()
    address = EmailAddress.objects.get(user=user)
    with pytest.raises(PermissionDenied):
        EmailAddress.objects.create(user=user, email="second@scholarsync.test")
    with pytest.raises(PermissionDenied):
        address.delete()


def test_guard_refuses_new_authenticators(guards: None) -> None:
    user = UserFactory.create()
    with pytest.raises(PermissionDenied):
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={})


def test_office_deactivating_a_demo_staff_account_is_403(
    client: Any, guards: None, public_demo: None
) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    staff_account = next(a for a in ACCOUNTS if a.role == User.Role.STAFF)
    with lockdown.bypass():
        staff = UserFactory.create(email=staff_account.email, role=User.Role.STAFF, verified=True)
    reauthenticated(client, office)
    response = client.post(reverse("office:staff-active", args=[staff.pk]), {"active": "0"})
    assert response.status_code == 403
    staff.refresh_from_db()
    assert staff.is_active


@pytest.mark.parametrize("view", ["office:staff-sessions", "office:staff-mfa"])
def test_office_cant_sign_out_or_strip_a_demo_account(
    client: Any, public_demo: None, view: str
) -> None:
    """Ending a shared account's sessions would sign out every visitor using it."""
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    staff_account = next(a for a in ACCOUNTS if a.role == User.Role.STAFF)
    with lockdown.bypass():
        staff = UserFactory.create(email=staff_account.email, role=User.Role.STAFF, verified=True)
    reauthenticated(client, office)
    response = client.post(reverse(view, args=[staff.pk]))
    assert response.status_code == 403
    assert FROZEN_HEADING in response.content.decode()


def test_office_can_still_sign_out_other_staff(client: Any, public_demo: None) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    staff = UserFactory.create(role=User.Role.STAFF, verified=True)
    reauthenticated(client, office)
    response = client.post(reverse("office:staff-sessions", args=[staff.pk]))
    assert response.status_code == 302


@pytest.mark.parametrize("index", range(len(ACCOUNTS)))
def test_demo_accounts_can_really_sign_in_with_guards_on(
    client: Any, guards: None, public_demo: None, index: int
) -> None:
    """A real sign-in writes the user (last login, maybe a rehash): the guards must allow it."""
    account = ACCOUNTS[index]
    _demo_account(account)
    response = client.post(reverse("account_login"), {"login": account.email, "password": PASSWORD})
    assert response.status_code == 302
    assert client.session.get("_auth_user_id")


def test_guards_are_registered_when_the_app_boots_in_public_demo(tmp_path: Any) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "SCHOLARSYNC_"))}
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "DJANGO_SECRET_KEY": "x" * 50,
            "DJANGO_ALLOWED_HOSTS": "scholarsync.example",
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "EMAIL_URL": "",
            "SCHOLARSYNC_PUBLIC_DEMO": "true",
            "CRON_SECRET": "c" * 32,
        }
    )
    code = (
        "import django; django.setup()\n"
        "from django.db.models.signals import pre_save, pre_delete\n"
        "from apps.demo import lockdown as l\n"
        "uids = {r[0][0] for r in pre_save.receivers} | {r[0][0] for r in pre_delete.receivers}\n"
        "need = {l.USER_GUARD, l.EMAIL_GUARD, l.EMAIL_DELETE_GUARD, l.AUTHENTICATOR_GUARD}\n"
        "print(sorted(need - uids))\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
