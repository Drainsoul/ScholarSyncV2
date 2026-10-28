import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e


def test_dialog_opens_and_returns_focus_on_escape(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/#overlays")
    opener = page.get_by_role("link", name="Release allowances")
    opener.click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(opener).to_be_focused()
    assert console_errors == []


def test_confirming_closes_the_dialog_and_toasts(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    dialog.get_by_role("button", name="Release allowances").click()
    expect(dialog).to_be_hidden()
    expect(page.locator("#toasts .toast--success")).to_contain_text(
        "Released ₱60,000.00 to 12 scholars"
    )
    assert console_errors == []


def test_dialog_link_works_without_javascript(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Release allowances")
    page.get_by_role("button", name="Release allowances").click()
    expect(page.locator("#toasts .toast--success")).to_contain_text("Released ₱60,000.00")
    context.close()


def test_bulk_bar_counts_the_selection(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#overlays")
    bar = page.locator("[data-bulk-bar]")
    approve = bar.get_by_role("button", name="Approve selected")
    expect(approve).to_be_disabled()
    page.get_by_label("Select David Shaw").check()
    page.get_by_label("Select William Heath").check()
    expect(bar).to_contain_text("2 selected")
    select_all = page.get_by_label("Select all applications")
    assert select_all.evaluate("(el) => el.indeterminate") is True
    select_all.check()
    expect(bar).to_contain_text("4 selected")
    approve.click()
    expect(page.locator("#toasts .toast--success")).to_contain_text("Approved 4 applications")
    assert console_errors == []
