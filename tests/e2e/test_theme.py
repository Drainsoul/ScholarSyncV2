"""The dark theme and the account menu's theme choice (spec §12 rev 29)."""

import pytest
from playwright.sync_api import Browser, Page, expect

from apps.accounts.tests.factories import UserFactory
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e

GROUND = "getComputedStyle(document.body).backgroundColor"
SCHEME = "getComputedStyle(document.documentElement).colorScheme"
LIGHT_GROUND = "rgb(245, 246, 248)"  # --slate-50
DARK_GROUND = "rgb(15, 21, 32)"  # --night-950


def test_the_app_follows_a_dark_device(page: Page, live_server, vite_build):
    page.emulate_media(color_scheme="dark")
    page.goto(f"{live_server.url}/accounts/login/")
    assert page.evaluate(GROUND) != LIGHT_GROUND
    page.emulate_media(color_scheme="light")
    assert page.evaluate(GROUND) != DARK_GROUND


def test_dark_can_be_pinned_from_the_account_menu_and_undone(
    page: Page, live_server, vite_build, console_errors
):
    user = UserFactory.create(verified=True)
    page.emulate_media(color_scheme="light")
    log_in(page, live_server.url, user.email, "/me/")
    page.get_by_role("button", name="Account menu").click()
    page.get_by_role("button", name="Dark").click()
    page.wait_for_url("**/me/")
    assert page.evaluate(SCHEME) == "dark"
    assert page.evaluate(GROUND) == DARK_GROUND
    # It sticks across pages, and the menu shows it.
    page.goto(f"{live_server.url}/me/profile/")
    assert page.evaluate(GROUND) == DARK_GROUND
    page.get_by_role("button", name="Account menu").click()
    expect(page.get_by_role("button", name="Dark")).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="System").click()
    page.wait_for_url("**/me/profile/")
    assert page.evaluate(SCHEME) == "light dark"
    assert page.evaluate(GROUND) == LIGHT_GROUND
    assert console_errors == []


def test_the_choice_works_without_javascript(browser: Browser, live_server, vite_build):
    user = UserFactory.create(verified=True)
    context = browser.new_context(java_script_enabled=False, color_scheme="dark")
    page = context.new_page()
    log_in(page, live_server.url, user.email, "/me/")
    # Without script the popover still opens from its button, natively.
    page.get_by_role("button", name="Account menu").click()
    page.get_by_role("button", name="Light").click()
    page.wait_for_url("**/me/")
    assert page.evaluate(GROUND) == LIGHT_GROUND
    context.close()
