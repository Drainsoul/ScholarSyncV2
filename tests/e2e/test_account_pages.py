import pytest
from playwright.sync_api import Page, ViewportSize, expect

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.e2e

SIZES: list[ViewportSize] = [{"width": 375, "height": 812}, {"width": 1280, "height": 800}]
URLS = ["/accounts/login/", "/accounts/signup/", "/accounts/password/reset/"]


@pytest.mark.parametrize("size", SIZES, ids=["phone", "desktop"])
@pytest.mark.parametrize("url", URLS)
def test_account_pages_have_no_console_errors(
    page: Page, live_server, vite_build, console_errors, url, size
):
    page.set_viewport_size(size)
    page.goto(f"{live_server.url}{url}")
    expect(page.get_by_role("heading", level=1)).to_have_count(1)
    assert page.evaluate("document.documentElement.scrollWidth") <= size["width"]
    assert console_errors == []


def test_signup_labels_work_for_the_flow_that_fills_them(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/accounts/signup/")
    page.get_by_label("Full name").fill("Ana Cruz")
    page.get_by_label("Email").fill("ana.cruz@scholarsync.test")
    page.get_by_label("Password", exact=True).fill("signup-pass-2026")
    page.get_by_label("Password (again)").fill("signup-pass-2026")
    page.get_by_label("I have read the privacy notice").check()
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Check your email")).to_be_visible()


def test_login_form_errors_are_announced(page: Page, live_server, vite_build, db):
    user = UserFactory.create(verified=True)
    page.goto(f"{live_server.url}/accounts/login/")
    page.locator("#login-form input[name=login]").fill(user.email)
    page.locator("#login-form input[name=password]").fill("not-the-password")
    page.get_by_role("button", name="Log in").click()
    summary = page.get_by_role("alert")
    expect(summary).to_be_visible()
    expect(summary).to_be_focused()
