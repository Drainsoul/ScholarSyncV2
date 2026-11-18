"""The idle warning in a real browser (M13, WCAG 2.2.1)."""

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.tests.factories import UserFactory
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e


def test_warning_keeps_the_session_or_signs_out(
    page: Page, live_server, vite_build, settings, console_errors
):
    settings.SESSION_IDLE_MINUTES_STUDENT = 0.2  # 12 seconds: the warning shows after 6
    student = UserFactory.create(verified=True)
    log_in(page, live_server.url, student.email, "/me/")
    page.wait_for_url(f"{live_server.url}/me/")
    dialog = page.locator("[data-session-dialog]")
    expect(dialog).to_be_visible(timeout=10_000)
    expect(dialog).to_contain_text("because you haven't done anything")
    page.get_by_role("button", name="Stay signed in").click()
    expect(dialog).to_be_hidden()
    expect(dialog).to_be_visible(timeout=10_000)  # the timer started again
    page.wait_for_url(f"{live_server.url}/accounts/login/**", timeout=15_000)
    expect(page.get_by_text("You were signed out after a period of inactivity.")).to_be_visible()
    assert console_errors == []
