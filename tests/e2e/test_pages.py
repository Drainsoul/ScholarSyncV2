import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

PHONE = {"width": 375, "height": 812}
DESKTOP = {"width": 1280, "height": 800}
PAGES = ["about", "privacy", "terms", "cookies", "help", "contact"]


@pytest.mark.parametrize("viewport", [PHONE, DESKTOP])
@pytest.mark.parametrize("name", PAGES)
def test_information_page_fits_and_has_no_csp_errors(
    page: Page, live_server, vite_build, console_errors, name, viewport
):
    page.set_viewport_size(viewport)
    page.goto(f"{live_server.url}/{name}/")
    expect(page.get_by_role("heading", level=1)).to_have_count(1)
    expect(page.get_by_role("contentinfo")).to_contain_text("Not affiliated with or endorsed")
    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    assert console_errors == []


@pytest.mark.parametrize("name", ["public", "auth", "student", "staff", "office"])
def test_footer_sits_below_the_content_in_every_layout(page: Page, live_server, vite_build, name):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    footer = page.locator("footer.footer")
    expect(footer).to_be_visible()
    box, main = footer.bounding_box(), page.locator("#main").bounding_box()
    assert box and main and box["y"] >= main["y"]
    assert page.evaluate("document.documentElement.scrollWidth") <= DESKTOP["width"]
