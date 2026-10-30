import pytest
from playwright.sync_api import Browser, Page, ViewportSize, expect

pytestmark = pytest.mark.e2e

PHONE: ViewportSize = {"width": 375, "height": 812}
DESKTOP: ViewportSize = {"width": 1280, "height": 800}
APP = ["student", "staff", "office"]


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
        if name in APP:
            expect(page.locator(".sidebar")).to_have_attribute("aria-label", "Main")
        expect(nav).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(nav).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
        if name in APP:
            box = page.locator(".sidebar").bounding_box()
            assert box and box["width"] == PHONE["width"]  # full width, above the content
            main = page.locator("#main").bounding_box()
            assert main and box["y"] + box["height"] <= main["y"]
    assert console_errors == []


@pytest.mark.parametrize("name", APP)
def test_sidebar_is_open_on_desktop(page: Page, live_server, vite_build, name):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def test_nav_is_visible_without_javascript_on_a_phone(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False, viewport=PHONE)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    context.close()


@pytest.mark.parametrize("name", APP)
def test_sidebar_is_248px_on_desktop(page: Page, live_server, vite_build, name):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    box = page.locator(".sidebar").bounding_box()
    assert box and box["x"] == 0
    assert box["width"] == 248
    topbar = page.locator(".topbar").bounding_box()
    assert topbar and topbar["x"] == 248


@pytest.mark.parametrize("name", ["public", "auth", "student", "staff", "office"])
@pytest.mark.parametrize("viewport", [PHONE, DESKTOP])
def test_logo_sits_beside_the_name(page: Page, live_server, vite_build, name, viewport):
    page.set_viewport_size(viewport)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    page.wait_for_load_state("load")  # nav.ts has run: the phone top bar shows its own brand
    brand = page.locator(".brand:visible")
    expect(brand).to_have_count(1)
    logo = brand.locator("> :first-child").bounding_box()  # the logo, or its red square
    wordmark = brand.locator(".brand__name").bounding_box()
    assert logo and wordmark
    assert 0 <= wordmark["x"] - (logo["x"] + logo["width"]) <= 16


@pytest.mark.parametrize("viewport", [PHONE, DESKTOP])
def test_account_menu_opens_to_sign_out(page: Page, live_server, vite_build, viewport):
    page.set_viewport_size(viewport)
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    if viewport == PHONE:
        page.get_by_role("button", name="Menu").click()
    sign_out = page.get_by_role("button", name="Sign out")
    expect(sign_out).to_be_hidden()
    page.locator(".account-menu > summary").click()
    expect(sign_out).to_be_visible()
    box = sign_out.bounding_box()
    assert (
        box and 0 <= box["y"] and box["y"] + box["height"] <= page.evaluate("innerHeight + scrollY")
    )
