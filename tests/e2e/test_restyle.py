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
