import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_money_uses_tabular_figures(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/_kit/mockups/disbursements/")
    for selector in (".figure__value", "td.num"):
        value = page.locator(selector).first.evaluate(
            "(el) => getComputedStyle(el).fontVariantNumeric"
        )
        assert "tabular-nums" in value, selector


def test_focus_is_visible_on_the_navy_top_bar(page: Page, live_server, vite_build):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    page.keyboard.press("Tab")  # skip link
    page.keyboard.press("Tab")  # brand link in the top bar
    focused = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement);"
        " return [document.activeElement.closest('.appbar') !== null,"
        " s.outlineStyle, s.boxShadow]; }"
    )
    assert focused[0] is True
    assert focused[1] != "none"
    assert focused[2] != "none"


def test_file_input_error_has_the_field_error_bar(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/_kit/")
    bar = page.locator(".file-input.field--invalid").evaluate(
        "(el) => [getComputedStyle(el).borderLeftWidth, getComputedStyle(el).borderLeftStyle]"
    )
    assert bar == ["4px", "solid"]


def test_current_tab_keeps_the_focus_halo(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/_kit/mockups/application-review/")
    tab = page.locator('.tabs a[aria-current="page"]')
    tab.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")  # keyboard focus, so :focus-visible applies
    style = tab.evaluate(
        "(el) => { const s = getComputedStyle(el);"
        " return [s.boxShadow, s.borderBottomWidth, s.borderBottomColor]; }"
    )
    assert "rgb(242, 183, 5)" in style[0]  # yellow halo
    assert style[1:] == ["3px", "rgb(184, 19, 42)"]  # and the current tab's red underline


def test_short_app_page_does_not_scroll(page: Page, live_server, vite_build):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    height = page.evaluate("[document.documentElement.scrollHeight, window.innerHeight]")
    assert height[0] == height[1]


def test_auth_form_starts_near_the_top_on_a_phone(page: Page, live_server, vite_build):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{live_server.url}/_kit/layouts/auth/")
    heading = page.locator("#main h1, #main h2").first
    top = heading.evaluate("(el) => el.getBoundingClientRect().top")
    assert top < 812 / 2


@pytest.mark.parametrize("slug", ["office-dashboard", "disbursements", "application-review"])
def test_page_header_drops_its_rule_above_figures_or_tabs(
    page: Page, live_server, vite_build, slug
):
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    rule = page.locator(".page-header").evaluate("(el) => getComputedStyle(el).borderBottomWidth")
    assert rule == "0px"
