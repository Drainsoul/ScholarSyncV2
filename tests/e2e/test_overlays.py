import pytest
from playwright.sync_api import Browser, Page, Route, expect

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
    count = bar.locator("[data-bulk-count]")
    expect(count).to_have_text("Select applications, then choose an action.")
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


SERVER_ERROR = "Something went wrong on our side. Try again."
NETWORK_ERROR = "We couldn't reach the server. Check your connection and try again."


def approve_first_row(page: Page) -> None:
    page.get_by_label("Select David Shaw").check()
    page.locator("[data-bulk-bar]").get_by_role("button", name="Approve selected").click()


def test_a_server_error_shows_a_danger_toast(page: Page, live_server, vite_build):
    page.route("**/_kit/demo/bulk/", lambda route: route.fulfill(status=500, body="Server error"))
    page.goto(f"{live_server.url}/_kit/#overlays")
    approve_first_row(page)
    expect(page.locator("#toasts .toast--danger")).to_have_text(SERVER_ERROR)


def test_a_network_error_shows_a_danger_toast(page: Page, live_server, vite_build):
    page.route("**/_kit/demo/bulk/", lambda route: route.abort("failed"))
    page.goto(f"{live_server.url}/_kit/#overlays")
    approve_first_row(page)
    expect(page.locator("#toasts .toast--danger")).to_have_text(NETWORK_ERROR)


def fail_posts(route: Route) -> None:
    if route.request.method == "POST":
        route.fulfill(status=500, body="Server error")
    else:
        route.continue_()


def test_toasts_are_visible_and_dismissible_over_an_open_dialog(
    page: Page, live_server, vite_build
):
    page.route("**/_kit/demo/dialog/", fail_posts)
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    dialog.get_by_role("button", name="Release allowances").click()
    toast = page.locator(".toast--danger").filter(has_text=SERVER_ERROR)
    expect(toast).to_be_visible()
    assert toast.evaluate("(el) => el.closest('[aria-live]') !== null && !el.closest('[inert]')")
    # A click lands only if the toast is above the modal and not inert.
    toast.get_by_role("button", name="Dismiss").click(timeout=5000)
    expect(toast).to_have_count(0)
    expect(dialog).to_be_visible()


def test_toasts_left_in_a_dialog_move_to_the_page_when_it_closes(
    page: Page, live_server, vite_build
):
    page.route("**/_kit/demo/dialog/", fail_posts)
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    dialog.get_by_role("button", name="Release allowances").click()
    expect(dialog.locator(".toast--danger")).to_have_text(SERVER_ERROR)
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(page.locator("#toasts .toast--danger")).to_have_text(SERVER_ERROR)
    expect(page.locator("#toasts .toast--danger")).to_be_visible()
