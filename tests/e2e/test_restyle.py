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
