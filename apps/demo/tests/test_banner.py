"""The public demo's banner (branch `demo`, docs/design/2026-11-28-hosted-demo-design.md 5.2)."""

from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db

COPY = "Data resets every night (around 03:00 Manila time)"


@pytest.fixture
def demo_installed(settings: Any) -> None:
    settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "apps.demo"]


def _sign_in(client: Any, role: str) -> str:
    if role == "anonymous":
        return "/accounts/login/"
    if role == "staff":
        membership = MembershipFactory.create(program=ProgramFactory.create(slug="tcu-ceaa"))
        client.force_login(membership.user)
        return "/staff/tcu-ceaa/"
    user = UserFactory.create(verified=True, role=User.Role(role))
    client.force_login(user)
    return "/office/" if role == User.Role.SUPER_ADMIN else "/me/"


@pytest.mark.parametrize("role", ["anonymous", "student", "staff", "super_admin"])
def test_banner_on_every_layout_in_public_demo(
    client: Any, settings: Any, demo_installed: None, vite_build: Any, role: str
) -> None:
    settings.PUBLIC_DEMO = True
    response = client.get(_sign_in(client, role))
    assert response.status_code == 200
    assert response.content.decode().count(COPY) == 1


def test_no_banner_outside_public_demo(
    client: Any, settings: Any, demo_installed: None, vite_build: Any
) -> None:
    settings.PUBLIC_DEMO = False
    assert COPY not in client.get("/accounts/login/").content.decode()


def test_banner_has_a_short_version_for_small_screens(
    client: Any, settings: Any, demo_installed: None, vite_build: Any
) -> None:
    """Phones get one short line; CSS shows exactly one of the two versions."""
    settings.PUBLIC_DEMO = True
    body = client.get("/accounts/login/").content.decode()
    assert body.count('class="demo-banner__text demo-banner__text--short"') == 1
    assert "Public demo · Resets nightly · No real data" in body
    assert body.count('class="demo-banner__text demo-banner__text--full"') == 1
