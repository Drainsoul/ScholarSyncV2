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
    toggle = page.get_by_role("button", name="Menu", exact=True)
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
    expect(page.get_by_role("button", name="Menu", exact=True)).to_be_hidden()
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def test_nav_is_visible_without_javascript_on_a_phone(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False, viewport=PHONE)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    expect(page.get_by_role("button", name="Menu", exact=True)).to_be_hidden()
    context.close()


@pytest.mark.parametrize("name", APP)
def test_sidebar_is_208px_on_desktop(page: Page, live_server, vite_build, name):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    box = page.locator(".sidebar").bounding_box()
    assert box and box["x"] == 0
    assert box["width"] == 208
    topbar = page.locator(".topbar").bounding_box()
    assert topbar and topbar["x"] == 208


@pytest.mark.parametrize("name", APP)
def test_page_is_centred_beside_the_sidebar_on_a_wide_screen(
    page: Page, live_server, vite_build, name
):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    topbar = page.locator(".topbar").bounding_box()
    box = page.locator(".app > .page").bounding_box()
    assert topbar and box and box["width"] == 1152  # --content-max
    left = box["x"] - topbar["x"]
    right = topbar["x"] + topbar["width"] - box["x"] - box["width"]
    assert left > 0 and abs(left - right) <= 1


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
        page.get_by_role("button", name="Menu", exact=True).click()
    sign_out = page.get_by_role("button", name="Sign out")
    expect(sign_out).to_be_hidden()
    page.get_by_role("button", name="Account menu").click()
    expect(sign_out).to_be_visible()
    box = sign_out.bounding_box()
    assert (
        box and 0 <= box["y"] and box["y"] + box["height"] <= page.evaluate("innerHeight + scrollY")
    )


@pytest.mark.parametrize("name", APP)
def test_phone_menu_opens_under_its_toggle_and_tab_enters_it(
    page: Page, live_server, vite_build, name
):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    toggle = page.get_by_role("button", name="Menu", exact=True)
    before = toggle.bounding_box()
    toggle.click()
    after = toggle.bounding_box()
    sidebar = page.locator(".sidebar").bounding_box()
    assert before and after and sidebar
    assert after["y"] == before["y"]  # the toggle stays put
    assert sidebar["y"] >= after["y"] + after["height"]
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.closest('nav.sidebar') !== null")


def test_nav_closes_on_escape(page: Page, live_server, vite_build, console_errors):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    toggle = page.get_by_role("button", name="Menu", exact=True)
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("navigation", name="Main")).to_be_hidden()
    expect(toggle).to_be_focused()
    assert console_errors == []


def test_page_load_toast_is_announced(page: Page, live_server, vite_build):
    """A toast rendered with the page is added to the live region after load, so it is read."""
    from apps.accounts.tests.factories import UserFactory
    from tests.e2e.flows import log_in

    page.add_init_script(
        """
        window.__toastAdds = 0;
        document.addEventListener("DOMContentLoaded", () => {
          const region = document.getElementById("toasts");
          if (region) new MutationObserver((records) => {
            for (const record of records) window.__toastAdds += record.addedNodes.length;
          }).observe(region, { childList: true });
        });
        """
    )
    student = UserFactory.create(verified=True)
    log_in(page, live_server.url, student.email, "/me/")  # sign-in leaves a "Signed in" toast
    # The enforced CSP refuses wait_for_function's string evaluation; poll instead.
    for _ in range(50):
        if page.evaluate("() => window.__toastAdds") > 0:
            break
        page.wait_for_timeout(100)
    assert page.evaluate("() => window.__toastAdds") > 0
    expect(page.locator("#toasts [data-toast]").first).to_be_visible()


def test_account_menu_closes_on_escape_and_outside_click(
    page: Page, live_server, vite_build, console_errors
):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    button = page.get_by_role("button", name="Account menu")
    sign_out = page.get_by_role("button", name="Sign out")
    button.click()
    expect(sign_out).to_be_visible()
    # Above its card, not centred in the viewport (anchor positioning or menus.ts).
    menu, card = sign_out.bounding_box(), button.bounding_box()
    assert menu and card and menu["y"] < card["y"]
    page.keyboard.press("Escape")
    expect(sign_out).to_be_hidden()
    expect(button).to_be_focused()
    button.click()
    expect(sign_out).to_be_visible()
    page.mouse.click(DESKTOP["width"] - 5, DESKTOP["height"] - 5)
    expect(sign_out).to_be_hidden()
    assert console_errors == []


def test_menus_are_placed_by_script_where_anchor_positioning_is_missing(
    browser: Browser, live_server, vite_build
):
    """menus.ts: in a browser without position-area the account menu would open centred; the script
    puts it above its card instead (simulated: CSS.supports says no, and position-area is off;
    bypass_csp lets the test inject that style under the enforced CSP)."""
    context = browser.new_context(bypass_csp=True, viewport=DESKTOP)
    page = context.new_page()
    page.add_init_script(
        """
        const supports = CSS.supports.bind(CSS);
        CSS.supports = (...args) => (args[0] === "position-area" ? false : supports(...args));
        document.addEventListener("DOMContentLoaded", () => {
            const style = document.createElement("style");
            style.textContent = ".menu-panel { position-area: none !important; }";
            document.head.append(style);
        });
        """
    )
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    button = page.get_by_role("button", name="Account menu")
    button.click()
    panel = page.locator("#account-menu")
    expect(panel).to_be_visible()
    menu, card = panel.bounding_box(), button.bounding_box()
    assert menu and card
    assert abs(menu["x"] - card["x"]) <= 1 and abs(menu["width"] - card["width"]) <= 1
    assert menu["y"] + menu["height"] <= card["y"]
    context.close()


def test_long_program_name_switcher_fits_at_375(page: Page, live_server, vite_build):
    from apps.programs.tests.factories import MembershipFactory, ProgramFactory
    from tests.e2e.flows import log_in

    long_name = (
        "Taguig City Scholarship for Exceptional Senior High School Graduates "
        "and Returning Learners"
    )
    program = ProgramFactory.create(slug="long", name=long_name)
    staff = MembershipFactory.create(program=program, user__verified=True).user
    MembershipFactory.create(
        program=ProgramFactory.create(slug="other", name="Other program"), user=staff
    )
    page.set_viewport_size(PHONE)
    log_in(page, live_server.url, staff.email, "/staff/long/")
    page.get_by_role("button", name="Menu", exact=True).click()
    page.locator(".switcher__button").first.click()
    expect(page.locator(".switcher .menu-panel").first).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
