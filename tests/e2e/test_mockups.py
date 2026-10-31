import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, ViewportSize, expect

from apps.kit.views import MOCKUPS

pytestmark = pytest.mark.e2e

VIEWPORTS: dict[str, ViewportSize] = {
    "phone": {"width": 375, "height": 812},
    "laptop": {"width": 1280, "height": 800},
    "desktop": {"width": 1440, "height": 900},
}
STAT_SLUGS = ["office-dashboard", "disbursements", "scholars"]
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


def test_drawer_works_without_javascript(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False, viewport=VIEWPORTS["desktop"])
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/mockups/scholars/?status=at_risk")
    expect(page.locator(".drawer")).to_have_count(0)
    page.get_by_role("link", name="Curtis Walker").click()
    drawer = page.locator("#scholar-drawer")
    expect(drawer).to_be_visible()
    expect(drawer.get_by_role("heading", name="Curtis Walker")).to_be_visible()
    assert "status=at_risk" in page.url
    box = drawer.bounding_box()
    assert box and round(box["width"]) == 400 and round(box["x"] + box["width"]) == 1440
    drawer.get_by_role("link", name="Close details").click()
    expect(page.locator(".drawer")).to_have_count(0)
    assert "status=at_risk" in page.url and "scholar=" not in page.url
    context.close()


def test_drawer_is_full_width_on_a_phone(page: Page, live_server, vite_build, console_errors):
    page.set_viewport_size(VIEWPORTS["phone"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/?scholar=13#scholar-drawer")
    drawer = page.locator("#scholar-drawer")
    expect(drawer).to_be_visible()
    width = drawer.evaluate("(el) => el.getBoundingClientRect().width")
    assert width == page.evaluate("window.innerWidth") == 375
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert console_errors == []


def test_renewal_marker_sits_at_80_percent(page: Page, live_server, vite_build):
    page.set_viewport_size(VIEWPORTS["desktop"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/?scholar=3#scholar-drawer")
    left = page.locator(".renewal__track").evaluate(
        """(el) => {
          const marker = getComputedStyle(el, "::after");
          return [parseFloat(marker.left) / el.getBoundingClientRect().width, marker.width];
        }"""
    )
    assert abs(left[0] - 0.8) < 0.01
    assert left[1] == "2px"
    gwa = page.locator(".renewal__gwa").evaluate("(el) => getComputedStyle(el).color")
    assert gwa == "rgb(155, 16, 34)"  # danger: Curtis Walker is below 80


# Every focusable element that is visible and intersects the drawer's box.
UNDER_THE_DRAWER = """() => {
  const box = document.querySelector("#scholar-drawer").getBoundingClientRect();
  const focusable = "a[href], button, input, select, textarea, summary, " +
    "[tabindex]:not([tabindex='-1'])";
  return [...document.querySelectorAll(focusable)]
    .filter((el) => !el.closest("#scholar-drawer") && el.getClientRects().length)
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width && r.height && r.left < box.right && r.right > box.left
        && r.top < box.bottom && r.bottom > box.top;
    })
    .map((el) => el.outerHTML.slice(0, 80));
}"""


def test_open_drawer_covers_no_focusable_control(page: Page, live_server, vite_build):
    page.set_viewport_size(VIEWPORTS["desktop"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/?scholar=4#scholar-drawer")
    expect(page.locator("#scholar-drawer")).to_be_visible()
    assert page.evaluate(UNDER_THE_DRAWER) == []
    assert page.evaluate("document.documentElement.scrollWidth") <= 1440


def test_phone_drawer_has_no_focus_halo(page: Page, live_server, vite_build):
    page.set_viewport_size(VIEWPORTS["phone"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/?scholar=4#scholar-drawer")
    page.locator("#scholar-drawer").focus()
    shadow = page.locator("#scholar-drawer").evaluate("(el) => getComputedStyle(el).boxShadow")
    assert shadow == "none"


def test_forced_colors_keep_the_current_nav_tab_and_chart(page: Page, live_server, vite_build):
    page.emulate_media(forced_colors="active")
    page.set_viewport_size(VIEWPORTS["desktop"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/")
    outline = "(el) => getComputedStyle(el).outlineStyle + getComputedStyle(el).outlineWidth"
    current = page.locator('.sidebar__list a[aria-current="page"]').first.evaluate(outline)
    other = page.locator(".sidebar__list a:not([aria-current])").first.evaluate(outline)
    assert current != other
    border = "(el) => getComputedStyle(el).borderBottomColor"
    assert page.locator('.tabs a[aria-current="page"]').evaluate(border) != page.locator(
        ".tabs a:not([aria-current])"
    ).first.evaluate(border)
    page.goto(f"{live_server.url}/_kit/mockups/office-dashboard/")
    bars = page.locator(".bar-chart__bar")
    background = "(el) => getComputedStyle(el).backgroundColor"
    canvas = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bars.first.evaluate(background) != canvas
    assert bars.first.evaluate(background) != bars.last.evaluate(background)


def test_account_menu_is_above_the_fold_at_1440_by_900(page: Page, live_server, vite_build):
    page.set_viewport_size(VIEWPORTS["desktop"])
    page.goto(f"{live_server.url}/_kit/mockups/scholars/")
    box = page.locator(".account-menu > summary").bounding_box()
    assert box and box["y"] >= 0 and box["y"] + box["height"] <= 900
