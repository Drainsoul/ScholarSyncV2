import pytest
from playwright.sync_api import Browser, Page, ViewportSize, expect

pytestmark = pytest.mark.e2e

PHONE: ViewportSize = {"width": 375, "height": 812}
DESKTOP: ViewportSize = {"width": 1280, "height": 800}


@pytest.mark.parametrize("name", ["public", "auth", "student", "staff", "office"])
def test_layout_fits_a_phone_and_nav_toggles(
    page: Page, live_server, vite_build, console_errors, name
):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
    toggle = page.get_by_role("button", name="Menu")
    if name == "auth":
        expect(toggle).to_have_count(0)
    else:
        nav = page.get_by_role("navigation", name="Main")
        expect(nav).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(nav).to_be_visible()
    assert console_errors == []


def test_sidebar_is_open_on_desktop(page: Page, live_server, vite_build):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def test_nav_is_visible_without_javascript_on_a_phone(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False, viewport=PHONE)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    context.close()
