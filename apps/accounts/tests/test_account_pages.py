"""Account pages in the app shell (spec §12 rev 26)."""

from typing import Any

import pytest
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.tests.auth import reauthenticated
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db

SIDEBAR = b'class="sidebar'
AUTH_PANEL = b'class="auth__panel"'


def _student() -> User:
    return UserFactory.create(verified=True)


def _staff() -> User:
    staff = UserFactory.create(role=User.Role.STAFF, verified=True)
    MembershipFactory.create(user=staff, program=ProgramFactory.create(name="TCU CEAA"))
    return staff


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)


@pytest.mark.parametrize("make", [_student, _staff, _office])
@pytest.mark.parametrize("url_name", ["usersessions_list", "mfa_index"])
def test_account_pages_render_in_the_users_own_shell(
    client: Client, vite_build: Any, make: Any, url_name: str
) -> None:
    user = make()
    client.force_login(user)
    page = client.get(reverse(url_name))
    assert page.status_code == 200
    assert SIDEBAR in page.content
    assert AUTH_PANEL not in page.content
    assert user.full_name.encode() in page.content


def test_staff_shell_shows_their_program(client: Client, vite_build: Any) -> None:
    client.force_login(_staff())
    assert b"TCU CEAA" in client.get(reverse("mfa_index")).content


def test_two_factor_overview_says_off_and_offers_setup(client: Client, vite_build: Any) -> None:
    client.force_login(_student())
    page = client.get(reverse("mfa_index")).content.decode()
    assert "Off: you sign in with your password only" in page
    assert "Set up the app" in page
    assert "Recovery codes" in page


def test_two_factor_overview_counts_recovery_codes(client: Client, vite_build: Any) -> None:
    user = _student()
    TOTP.activate(user, generate_totp_secret())
    RecoveryCodes.activate(user)
    client.force_login(user)
    page = client.get(reverse("mfa_index")).content.decode()
    assert "On: you sign in with your password and a code from your phone" in page
    assert "10 of 10 left" in page
    assert "Turn off" in page


def test_setup_page_shows_three_steps_and_the_key(client: Client, vite_build: Any) -> None:
    user = _student()
    reauthenticated(client, user)
    page = client.get(reverse("mfa_activate_totp"))
    assert page.status_code == 200
    content = page.content.decode()
    assert SIDEBAR in page.content
    assert "Scan this code with the app" in content
    assert 'id="authenticator_secret"' in content
    assert "data:image/svg+xml;base64," in content


def test_sign_in_pages_keep_the_sign_in_layout(client: Client, vite_build: Any) -> None:
    page = client.get(reverse("account_login"))
    assert AUTH_PANEL in page.content
    assert SIDEBAR not in page.content
