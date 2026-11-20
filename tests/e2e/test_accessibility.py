"""WCAG 2.2 A/AA on every key screen, checked by axe-core at desktop and phone widths (M12).

The manual half of the audit is `docs/accessibility/wcag-22-aa.md`."""

from typing import Any

import pytest
from playwright.sync_api import Browser, ViewportSize

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from tests.e2e.conftest import axe_violations
from tests.e2e.flows import log_in
from tests.worlds import build_world

pytestmark = pytest.mark.e2e

WIDTHS: list[ViewportSize] = [{"width": 1280, "height": 900}, {"width": 375, "height": 812}]

SCREENS: dict[str, list[str]] = {
    "anonymous": ["/", "/programs/", "/programs/tcu-ceaa/", "/accounts/login/", "/about/"],
    "student": [
        "/me/",
        "/me/profile/",
        "/me/match/",
        "applications:detail",
        "/me/applications/",
        "/me/scholarships/",
        "/me/notifications/",
        "/accounts/sessions/",
        "/accounts/2fa/",
    ],
    "staff": [
        "/staff/tcu-ceaa/",
        "/staff/tcu-ceaa/applications/",
        "review:detail",
        "/staff/tcu-ceaa/scholars/",
        "scholars:detail",
        "/staff/tcu-ceaa/disbursements/",
        "/staff/tcu-ceaa/reports/",
        "reports:detail",
        "/staff/tcu-ceaa/tasks/",
    ],
    "head": [
        "/staff/tcu-ceaa/settings/",
        "/staff/tcu-ceaa/settings/tiers/",
        "/staff/tcu-ceaa/audit/",
    ],
    "office": [
        "/office/",
        "/office/programs/",
        "/office/staff/",
        "/office/analytics/",
        "/office/scholars/",
        "/office/audit/",
        "/office/reports/",
        "/office/support/",
        "/office/tasks/",
    ],
}


@pytest.fixture
def people() -> dict[str, Any]:
    tcu = ProgramFactory.create(
        slug="tcu-ceaa", name="TCU CEAA", description="City allowance for TCU students."
    )
    ProgramFactory.create(slug="lani", name="LANI")
    return {
        "anonymous": None,
        "student": UserFactory.create(verified=True),
        "staff": MembershipFactory.create(program=tcu, user__verified=True).user,
        "head": MembershipFactory.create(
            program=tcu, level=ProgramMembership.Level.HEAD, user__verified=True
        ).user,
        "office": UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True),
    }


@pytest.mark.parametrize("persona", list(SCREENS))
def test_key_screens_have_no_axe_violations(
    persona: str,
    people: dict[str, Any],
    browser: Browser,
    live_server: Any,
    vite_build: Any,
    axe_source: str,
) -> None:
    from django.urls import reverse

    world = build_world(people)
    base = live_server.url
    found: list[str] = []
    for viewport in WIDTHS:
        context = browser.new_context(bypass_csp=True, viewport=viewport)
        page = context.new_page()
        user = people[persona]
        if user is not None:
            log_in(page, base, user.email, "/")
        for screen in SCREENS[persona]:
            path = screen if screen.startswith("/") else reverse(screen, kwargs=world[screen])
            response = page.goto(f"{base}{path}")
            assert response is not None and response.status == 200, (path, persona)
            for violation in axe_violations(page, axe_source):
                found.append(
                    f"{viewport['width']}px {path}: {violation['id']} ({violation['impact']}) "
                    f"at {violation['target']}: {violation['help']}"
                )
        context.close()
    assert found == [], "\n".join(found)


@pytest.mark.parametrize("persona", ["anonymous", "student", "staff", "office"])
def test_reflow_at_320px(
    persona: str, people: dict[str, Any], browser: Browser, live_server: Any, vite_build: Any
) -> None:
    """1.4.10 Reflow: no page-level horizontal scroll at 320 CSS px (tables scroll inside
    their own region, which WCAG allows)."""
    from django.urls import reverse

    world = build_world(people)
    base = live_server.url
    context = browser.new_context(viewport={"width": 320, "height": 640})
    page = context.new_page()
    user = people[persona]
    if user is not None:
        log_in(page, base, user.email, "/")
    wide: list[str] = []
    for screen in SCREENS[persona]:
        path = screen if screen.startswith("/") else reverse(screen, kwargs=world[screen])
        page.goto(f"{base}{path}")
        if not page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"):
            wide.append(path)
    context.close()
    assert wide == []


def test_keyboard_only_sign_in(
    people: dict[str, Any], browser: Browser, live_server: Any, vite_build: Any
) -> None:
    """2.1.1 Keyboard and 2.4.7 Focus visible: sign in with Tab, typing and Enter only."""
    from apps.accounts.tests.factories import DEFAULT_PASSWORD

    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{live_server.url}/accounts/login/")
    page.locator("#login-form input[name=login]").focus()
    page.keyboard.type(people["student"].email)
    order = []
    for _ in range(4):  # Tab through whatever sits between the fields until the password box
        page.keyboard.press("Tab")
        order.append(page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
        if page.evaluate("document.activeElement.name") == "password":
            break
    assert page.evaluate("document.activeElement.name") == "password", order
    page.keyboard.type(DEFAULT_PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_url(f"{live_server.url}/me/")
    page.keyboard.press("Tab")
    focused = page.evaluate(
        "getComputedStyle(document.activeElement).outlineStyle + ' ' + "
        "getComputedStyle(document.activeElement).boxShadow"
    )
    assert focused.strip() not in {"none none", ""}
    context.close()
