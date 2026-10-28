"""The filter + sortable table + pagination pattern (spec §12) that staff lists copy."""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_filtering_keeps_the_column_sort(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/")
    page.locator("#sort-school").click()
    expect(page).to_have_url(re.compile(r"sort=school"))
    page.get_by_label("Name", exact=True).fill("r")
    expect(page.locator("#scholars-count")).to_have_text("5 scholars")
    names = page.locator("#scholars-table tbody th")
    # By school; sorting by name would put Carolyn Hawkins first.
    expect(names).to_have_text(
        ["Curtis Walker", "Karen Willis", "Krista Kelley", "Carolyn Hawkins", "Shannon Briggs"]
    )
    expect(page.locator("#scholars-table th[aria-sort]")).to_have_text("School")
    expect(page).to_have_url(re.compile(r"[?&]q=r\b"))
    assert page.url.count("sort=") == 1
    assert "sort=school" in page.url
    assert console_errors == []


def test_clear_filters_resets_the_inputs_and_the_table(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/")
    page.locator("#filter-status").select_option("ended")
    page.get_by_label("Name", exact=True).fill("nobody-has-this-name")
    clear = page.get_by_role("link", name="Clear filters")
    expect(clear).to_be_visible()
    clear.click()
    expect(page.locator("#scholars-table tbody tr")).to_have_count(5)
    expect(page.get_by_label("Name", exact=True)).to_have_value("")
    expect(page.locator("#filter-status")).to_have_value("")
    assert console_errors == []


def test_keyboard_sorting_keeps_focus_on_the_sort_link(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/")
    page.locator("#sort-school").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#scholars-table th[aria-sort]")).to_have_text("School")
    expect(page.locator("#sort-school")).to_be_focused()
    assert page.evaluate("document.activeElement.id") == "sort-school"
    assert console_errors == []


def test_paging_keeps_focus_on_the_page_link(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/")
    page.locator("#page-next").focus()
    page.keyboard.press("Enter")
    expect(page.locator(".pagination__status")).to_have_text("Page 2 of 3")
    expect(page.locator("#page-next")).to_be_focused()
    assert console_errors == []


def test_result_count_is_announced_after_filtering(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/")
    status = page.get_by_role("status").filter(has_text="scholar")
    expect(status).to_have_text("12 scholars")
    page.get_by_label("Name", exact=True).fill("shaw")
    expect(page.locator("#scholars-table tbody tr")).to_have_count(1)
    expect(status).to_have_text("1 scholar")
    expect(page.locator("#scholars-count")).to_have_count(1)
    assert page.locator("#scholars-table #scholars-count").count() == 0
    assert console_errors == []
