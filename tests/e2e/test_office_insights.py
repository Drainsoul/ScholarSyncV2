"""Analytics, scholars across programs and the audit log in a browser (M11c)."""

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.awards.tests.factories import AwardFactory
from apps.core.audit import record
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import AcademicTermFactory, MembershipFactory, ProgramFactory
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e

PHONE: ViewportSize = {"width": 375, "height": 800}


def test_office_analytics_scholars_and_audit_pages(
    page: Page, live_server, vite_build, console_errors
):
    term = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    AwardFactory.create(source_application__program=program, source_application__term=term)
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    record(actor=office, action="program.updated", program=program, data={"program": program.pk})
    base = live_server.url
    page.set_viewport_size(PHONE)
    log_in(page, base, office.email, "/office/analytics/")
    for path in ("/office/analytics/", "/office/scholars/", "/office/audit/"):
        page.goto(f"{base}{path}")
        expect(page.locator("h1")).to_have_count(1)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path

    page.goto(f"{base}/office/analytics/")
    page.get_by_text("View as table").click()
    expect(page.get_by_role("cell", name="0").first).to_be_visible()
    with page.expect_download() as info:
        page.get_by_role("link", name="Download summary").click()
    assert info.value.suggested_filename == "program-summary-2026-2027.xlsx"

    page.goto(f"{base}/office/scholars/")
    with page.expect_download() as info:
        page.get_by_role("link", name="Download CSV").click()
    assert info.value.suggested_filename.startswith("scholars-all-active-")

    page.goto(f"{base}/office/audit/")
    expect(page.get_by_text("Edited a program").first).to_be_visible()
    assert console_errors == []


def test_head_audit_log_and_staff_has_no_link(page: Page, live_server, vite_build):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    head = MembershipFactory.create(
        program=program, level=ProgramMembership.Level.HEAD, user__verified=True
    ).user
    staff = MembershipFactory.create(program=program, user__verified=True).user
    record(actor=staff, action="award.created", program=program, data={"award": 7})
    base = live_server.url

    log_in(page, base, head.email, "/staff/tcu-ceaa/")
    page.get_by_role("link", name="Audit log").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Audit log")
    expect(page.get_by_text("Added a scholar")).to_be_visible()

    page.context.clear_cookies()
    log_in(page, base, staff.email, "/staff/tcu-ceaa/")
    expect(page.get_by_role("link", name="Audit log")).to_have_count(0)
    response = page.goto(f"{base}/staff/tcu-ceaa/audit/")
    assert response is not None and response.status == 403
