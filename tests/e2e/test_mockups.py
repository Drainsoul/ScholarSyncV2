import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from apps.kit.views import MOCKUPS

pytestmark = pytest.mark.e2e

VIEWPORTS: dict[str, ViewportSize] = {
    "phone": {"width": 375, "height": 812},
    "desktop": {"width": 1440, "height": 900},
}


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_mockup_fits_and_has_no_errors(
    page: Page, live_server, vite_build, console_errors, slug, viewport
):
    size = VIEWPORTS[viewport]
    page.set_viewport_size(size)
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= size["width"]
    assert console_errors == []
    if folder := os.environ.get("MOCKUP_SCREENSHOTS"):
        page.screenshot(path=Path(folder) / f"{slug}-{viewport}.png", full_page=True)
