import re

import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e

PAYLOAD = '<img src=x onerror="window.pwned=1">'


def test_htmx_toast_shows_text_not_markup(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_label("Message", exact=True).fill(PAYLOAD)
    page.get_by_role("button", name="Show success").click()
    toast = page.locator("#toasts .toast")
    expect(toast).to_have_count(1)
    expect(toast).to_contain_text(PAYLOAD)
    expect(page.locator("#toasts img")).to_have_count(0)
    assert page.evaluate("window.pwned") is None
    assert console_errors == []


def test_success_toasts_hide_but_errors_stay(page: Page, live_server, vite_build):
    page.clock.install()
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_role("button", name="Show success").click()
    page.get_by_role("button", name="Show error").click()
    expect(page.locator("#toasts .toast")).to_have_count(2)
    page.mouse.move(0, 0)
    page.clock.run_for(9000)
    expect(page.locator("#toasts .toast")).to_have_count(1)
    danger = page.locator("#toasts .toast--danger")
    expect(danger).to_be_visible()
    danger.get_by_role("button", name="Dismiss").click()
    expect(page.locator("#toasts .toast")).to_have_count(0)


def test_toast_without_javascript_comes_from_django_messages(
    browser: Browser, live_server, vite_build
):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_role("button", name="Show warning").click()
    expect(page.locator("#toasts .toast--warning")).to_contain_text("Application saved")
    context.close()


def test_filtering_swaps_only_the_table_and_keeps_history_out_of_storage(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/")
    rows = page.locator("#scholars-table tbody tr")
    expect(rows).to_have_count(5)
    page.get_by_label("Name", exact=True).fill("shaw")
    expect(rows).to_have_count(1)
    expect(page).to_have_url(re.compile(r"q=shaw"))
    expect(page.locator("h1")).to_have_count(1)
    expect(page.locator("#scholars-table")).to_have_count(1)
    assert page.evaluate("window.localStorage.length") == 0
    assert console_errors == []
