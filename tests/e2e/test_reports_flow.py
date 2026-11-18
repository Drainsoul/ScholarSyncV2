"""A report goes to the office, comes back, goes again and is accepted (M11c)."""

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from tests.e2e.flows import log_in, one_kb_pdf, payload

pytestmark = pytest.mark.e2e


def _bell(page: Page, unread: int) -> None:
    expect(page.locator(".topbar__bell")).to_have_attribute(
        "aria-label", f"Notifications, {unread} unread"
    )


def _switch(page: Page, base: str, email: str, next_path: str) -> None:
    page.context.clear_cookies()
    log_in(page, base, email, next_path)


def test_staff_sends_report_office_returns_staff_resends_office_accepts(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    base = live_server.url

    log_in(page, base, staff.email, "/staff/tcu-ceaa/reports/new/")
    page.get_by_label("Title").fill("Quarterly update")
    page.get_by_label("Period from").fill("2026-08-01")
    page.get_by_label("Period to").fill("2026-10-31")
    page.locator("input[type=file]").set_input_files(
        files=payload("q3-report.pdf", "application/pdf", one_kb_pdf())
    )
    expect(page.locator(".file-input__status")).to_have_text("q3-report.pdf uploaded")
    page.get_by_role("button", name="Send report").click()
    expect(page.get_by_text("Report sent to the scholarship office.")).to_be_visible()
    expect(page.get_by_role("link", name="q3-report.pdf")).to_be_visible()

    _switch(page, base, office.email, "/office/")
    _bell(page, 1)
    page.locator(".topbar__bell").click()
    page.get_by_role("link", name="TCU CEAA sent a report for review").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Quarterly update")
    page.get_by_label("Return to the program").check()
    page.get_by_label("Note to the program").fill("Add the September totals.")
    page.get_by_role("button", name="Save decision").click()
    expect(page.get_by_text("Report returned to TCU CEAA.")).to_be_visible()

    _switch(page, base, staff.email, "/staff/tcu-ceaa/")
    _bell(page, 1)
    page.locator(".topbar__bell").click()
    page.get_by_role("link", name="The office returned your TCU CEAA report").click()
    expect(page.get_by_text("Add the September totals.")).to_be_visible()
    page.get_by_label("Description").fill("September totals added.")
    page.get_by_role("button", name="Send again").click()
    expect(page.get_by_text("Report sent again.")).to_be_visible()

    _switch(page, base, office.email, "/office/reports/")
    page.get_by_role("link", name="Quarterly update").click()
    expect(page.get_by_text("Returned earlier: Add the September totals.")).to_be_visible()
    page.get_by_role("button", name="Save decision").click()
    expect(page.get_by_text("Report accepted.")).to_be_visible()

    _switch(page, base, staff.email, "/staff/tcu-ceaa/reports/")
    expect(page.get_by_role("link", name="Quarterly update")).to_be_visible()
    expect(page.locator("tbody")).to_contain_text("Accepted")
    assert console_errors == []
