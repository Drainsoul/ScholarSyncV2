"""A staff report goes to the head, then the office; it comes back, goes again through the head
and is accepted (M11c, rev 33)."""

import pytest
from playwright.sync_api import Browser, Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from tests.e2e.conftest import axe_violations
from tests.e2e.flows import log_in, one_kb_pdf, one_page_pdf, payload

pytestmark = pytest.mark.e2e


def _bell(page: Page, unread: int) -> None:
    expect(page.locator(".topbar__bell")).to_have_attribute(
        "aria-label", f"Notifications, {unread} unread"
    )


def _switch(page: Page, base: str, email: str, next_path: str) -> None:
    page.context.clear_cookies()
    log_in(page, base, email, next_path)


def _head_approves_and_sends(page: Page, base: str, email: str, bell: int) -> None:
    _switch(page, base, email, "/staff/tcu-ceaa/")
    _bell(page, bell)
    page.locator(".topbar__bell").click()
    page.get_by_role("link", name="A TCU CEAA report is waiting for your review").first.click()
    expect(page.get_by_role("heading", name="Your review")).to_be_visible()
    page.get_by_role("button", name="Approve").click()
    expect(
        page.get_by_text("Report approved. Send it to the scholarship office next.")
    ).to_be_visible()
    page.get_by_role("button", name="Send to the scholarship office").click()
    expect(page.get_by_text("Report sent to the scholarship office.")).to_be_visible()
    expect(page.locator(".page-header__meta")).to_contain_text("Waiting for the office")


def test_staff_sends_report_head_sends_office_returns_staff_resends_office_accepts(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    head = MembershipFactory.create(program=program, level="head", user__verified=True).user
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
    expect(page.get_by_text("Report sent to the program head for review.")).to_be_visible()
    expect(page.get_by_role("link", name="q3-report.pdf", exact=True)).to_be_visible()

    _head_approves_and_sends(page, base, head.email, 1)

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
    _bell(page, 2)  # the head's approval, then the office's return
    page.locator(".topbar__bell").click()
    page.get_by_role("link", name="The office returned your TCU CEAA report").click()
    expect(page.get_by_text("Add the September totals.")).to_be_visible()
    page.get_by_label("Description").fill("September totals added.")
    page.get_by_role("button", name="Send again").click()
    expect(page.get_by_text("Report sent to the head again.")).to_be_visible()

    # The office's return reached the head who sent it too; the report waits for them again.
    _head_approves_and_sends(page, base, head.email, 2)

    _switch(page, base, office.email, "/office/reports/")
    page.get_by_role("link", name="Quarterly update").click()
    expect(page.get_by_text("Returned earlier: Add the September totals.")).to_be_visible()
    page.get_by_role("button", name="Save decision").click()
    expect(page.get_by_text("Report accepted.")).to_be_visible()

    _switch(page, base, staff.email, "/staff/tcu-ceaa/reports/")
    expect(page.get_by_role("link", name="Quarterly update")).to_be_visible()
    expect(page.locator("tbody")).to_contain_text("Accepted")
    assert console_errors == []


def test_office_previews_a_report_pdf(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    from apps.files import storage
    from apps.reports.tests.factories import ReportFileFactory

    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    row = ReportFileFactory.create(report__title="Quarterly scholar update")
    storage.put(key=row.file.final_key, body=one_page_pdf(), content_type="application/pdf")
    log_in(page, live_server.url, office.email, f"/office/reports/{row.report.pk}/")
    page.get_by_role("link", name="Preview report.pdf").click()
    dialog = page.get_by_role("dialog", name="Quarterly scholar update")
    expect(dialog.get_by_role("img", name="Page 1 of 1")).to_be_visible()
    expect(dialog.locator("[data-pdf-status]")).to_have_text("1 page")
    assert console_errors == []


def test_head_review_screens_have_no_axe_violations(
    browser: Browser, live_server, vite_build, axe_source: str
):
    from apps.reports.tests.factories import ReportFactory, ReportFileFactory

    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    head = MembershipFactory.create(program=program, level="head", user__verified=True).user
    waiting = ReportFactory.create(program=program, status="with_head")
    approved = ReportFactory.create(program=program, status="approved")
    for report in (waiting, approved):
        ReportFileFactory.create(report=report)
    base = live_server.url
    found: list[str] = []
    for scheme in ("light", "dark"):
        context = browser.new_context(bypass_csp=True, color_scheme=scheme)
        page = context.new_page()
        log_in(page, base, head.email, "/staff/tcu-ceaa/")
        for path in (
            f"/staff/tcu-ceaa/reports/{waiting.pk}/",
            f"/staff/tcu-ceaa/reports/{approved.pk}/",
            "/staff/tcu-ceaa/reports/?tab=with_head",
            "/staff/tcu-ceaa/",
        ):
            page.goto(f"{base}{path}")
            for violation in axe_violations(page, axe_source):
                found.append(f"{scheme} {path}: {violation['id']} at {violation['target']}")
        context.close()
    assert found == [], "\n".join(found)
