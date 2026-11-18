"""Security behaviour in a real browser (M12)."""

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e


def test_signed_in_page_is_no_store_and_csp_enforced(page: Page, live_server, vite_build):
    student = UserFactory.create(verified=True)
    log_in(page, live_server.url, student.email, "/me/")
    response = page.goto(f"{live_server.url}/me/")
    assert response is not None and response.status == 200
    headers = response.headers
    assert "no-store" in headers["cache-control"]
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "content-security-policy-report-only" not in headers


def test_sign_in_appears_in_the_office_audit_log(page: Page, live_server, vite_build):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(
        program=program, user__verified=True, user__full_name="Krista Kelley"
    ).user
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    log_in(page, live_server.url, staff.email, "/staff/tcu-ceaa/")
    page.wait_for_url(f"{live_server.url}/staff/tcu-ceaa/")
    page.context.clear_cookies()
    log_in(page, live_server.url, office.email, "/office/audit/?group=accounts")
    expect(page.get_by_role("heading", level=1)).to_have_text("Audit log")
    row = page.locator("tbody tr", has_text="Krista Kelley")
    expect(row.first).to_contain_text("Signed in")
