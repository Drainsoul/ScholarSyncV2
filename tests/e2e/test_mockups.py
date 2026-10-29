import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from apps.kit.views import MOCKUPS

pytestmark = pytest.mark.e2e

VIEWPORTS: dict[str, ViewportSize] = {
    "phone": {"width": 375, "height": 812},
    "laptop": {"width": 1280, "height": 800},
    "desktop": {"width": 1440, "height": 900},
}
STAT_SLUGS = ["office-dashboard", "disbursements"]
# Each figure value whose text runs past its figure (bounding boxes, so visible overflow counts).
OVERFLOWING_STATS = """() => [...document.querySelectorAll(".figure__value")]
  .filter((value) => {
    const tile = value.closest(".figure").getBoundingClientRect();
    const text = document.createRange();
    text.selectNodeContents(value);
    const box = text.getBoundingClientRect();
    return box.right > tile.right || box.left < tile.left || value.scrollWidth > value.clientWidth;
  })
  .map((value) => value.textContent)"""
# Each figure value that wraps onto a second line (money must never break mid-number).
WRAPPING_STATS = """() => [...document.querySelectorAll(".figure__value")]
  .filter((value) => {
    const text = document.createRange();
    text.selectNodeContents(value);
    const tops = new Set([...text.getClientRects()].map((rect) => Math.round(rect.top)));
    return tops.size > 1;
  })
  .map((value) => value.textContent)"""


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
        # Settled styles: a load-time transition must not leave a half-faded button in the shot.
        page.screenshot(
            path=Path(folder) / f"{slug}-{viewport}.png", full_page=True, animations="disabled"
        )


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("slug", STAT_SLUGS)
def test_stat_values_stay_inside_their_tiles(page: Page, live_server, vite_build, slug, viewport):
    page.set_viewport_size(VIEWPORTS[viewport])
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    page.evaluate("document.fonts.ready")
    assert page.locator(".figure__value").count() >= 4
    assert page.evaluate(OVERFLOWING_STATS) == []


@pytest.mark.parametrize("width", [375, 768, 1024, 1280, 1440])
@pytest.mark.parametrize("slug", STAT_SLUGS)
def test_money_figures_never_break_mid_number(page: Page, live_server, vite_build, slug, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    page.evaluate("document.fonts.ready")
    assert page.evaluate(WRAPPING_STATS) == []
    assert page.evaluate(OVERFLOWING_STATS) == []


# Each element inside a panel that pokes out of it, and each panel table that scrolls sideways.
CLIPPED_IN_PANELS = """() => {
  const out = [];
  for (const card of document.querySelectorAll(".card")) {
    const box = card.getBoundingClientRect();
    for (const el of card.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.width <= 1 || r.height <= 1) continue;  // visually hidden text
      if (r.left < box.left - 0.5 || r.right > box.right + 0.5) out.push(el.outerHTML.slice(0, 80));
    }
    for (const wrap of card.querySelectorAll(".table-wrap")) {
      const name = wrap.getAttribute("aria-labelledby");
      if (wrap.scrollWidth > wrap.clientWidth) out.push(`scrolls: ${name}`);
    }
  }
  return out;
}"""


@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_nothing_in_a_panel_is_clipped_on_a_phone(page: Page, live_server, vite_build, slug):
    page.set_viewport_size(VIEWPORTS["phone"])
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    page.evaluate("document.fonts.ready")
    assert page.evaluate(CLIPPED_IN_PANELS) == []


def test_file_links_keep_the_icon_with_the_name(page: Page, live_server, vite_build):
    page.set_viewport_size(VIEWPORTS["phone"])
    page.goto(f"{live_server.url}/_kit/mockups/application-review/")
    page.evaluate("document.fonts.ready")
    # One line tall: an icon on a line of its own, or a name broken mid-word, makes it taller.
    tall = page.evaluate(
        """() => [...document.querySelectorAll(".file-link")].filter((link) => {
          const lineHeight = parseFloat(getComputedStyle(link).fontSize) * 1.6;
          return link.getBoundingClientRect().height > lineHeight;
        }).map((link) => link.textContent)"""
    )
    assert page.locator(".file-link").count() == 4
    assert tall == []


def test_panel_header_text_has_no_stray_margin(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/_kit/mockups/application-review/")
    margins = page.locator(".card__header > p").evaluate_all(
        "(els) => els.map((el) => getComputedStyle(el).marginBottom)"
    )
    assert margins and set(margins) == {"0px"}


@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_no_transition_runs_on_load(page: Page, live_server, vite_build, slug):
    """Buttons used to fade in on load: a size container restyled its contents after load."""
    page.add_init_script(
        "window.__transitions = [];"
        "document.addEventListener('transitionrun', (event) =>"
        " window.__transitions.push(event.target.className), true);"
    )
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    page.wait_for_timeout(400)
    assert page.evaluate("window.__transitions") == []
