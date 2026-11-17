import re

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e

NEW_PASSWORD = "a-brand-new-pass-2026"


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)


def confirm_password_if_asked(page: Page) -> None:
    """Sensitive changes may stop at the password page; allauth replays the form after it."""
    page.wait_for_load_state()
    if "/accounts/reauthenticate/" in page.url:
        page.locator("input[name=password]").fill(DEFAULT_PASSWORD)
        page.get_by_role("button", name="Confirm").click()


def test_office_opens_a_new_program(page: Page, live_server, vite_build, console_errors):
    AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    base = live_server.url
    log_in(page, base, _office().email, "/office/programs/new/")
    page.get_by_label("Short name for links").fill("arts-grant")
    page.get_by_label("Program name").fill("Taguig Arts Grant")
    page.get_by_role("button", name="Create program").click()
    expect(page.get_by_text("Taguig Arts Grant is closed.")).to_be_visible()

    page.goto(f"{base}/office/programs/")
    page.get_by_role("button", name="Open Taguig Arts Grant").click()
    expect(
        page.get_by_text(
            "Add an allowance tier and a required document before opening Taguig Arts Grant."
        )
    ).to_be_visible()

    page.goto(f"{base}/staff/arts-grant/settings/tiers/new/")
    page.get_by_label("Code").fill("standard")
    page.get_by_label("Name").fill("Standard")
    page.get_by_label("Allowance per term (₱)").fill("4000")
    page.get_by_role("button", name="Add tier").click()
    confirm_password_if_asked(page)
    expect(page.get_by_text("Tier added.")).to_be_visible()

    page.goto(f"{base}/staff/arts-grant/settings/documents/")
    page.get_by_label("Code").fill("registration")
    page.get_by_role("textbox", name=re.compile(r"^Document")).fill("Certificate of registration")
    page.get_by_role("button", name="Add document").click()
    expect(page.get_by_text("Document added.")).to_be_visible()

    page.goto(f"{base}/office/programs/")
    page.get_by_role("button", name="Open Taguig Arts Grant").click()
    expect(page.get_by_text("Taguig Arts Grant is open.")).to_be_visible()
    page.goto(f"{base}/programs/")
    expect(page.get_by_text("Taguig Arts Grant").first).to_be_visible()
    assert console_errors == []


def test_office_creates_staff_who_sets_a_password(browser, live_server, vite_build, mailoutbox):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    base = live_server.url
    office_page = browser.new_page()
    log_in(office_page, base, _office().email, "/office/staff/new/")
    office_page.get_by_label("Full name").fill("Ana Reyes")
    office_page.get_by_label("Email").fill("ana.reyes@scholarsync.test")
    office_page.get_by_label("Program staff").check()
    office_page.get_by_role("button", name="Create account").click()
    confirm_password_if_asked(office_page)
    expect(office_page.get_by_text("Account created.", exact=False)).to_be_visible()

    welcome = next(mail for mail in mailoutbox if "ana.reyes@scholarsync.test" in mail.to)
    match = re.search(r"https?://\S+/accounts/password/reset/key/\S+/", welcome.body)
    assert match is not None
    staff_page = browser.new_page()
    # The link carries the configured site address; the test server listens elsewhere.
    staff_page.goto(re.sub(r"^https?://[^/]+", base, match.group(0)))
    staff_page.locator("input[name=password1]").fill(NEW_PASSWORD)
    staff_page.locator("input[name=password2]").fill(NEW_PASSWORD)
    staff_page.locator("form button[type=submit]").first.click()

    staff_page.goto(f"{base}/accounts/login/")
    staff_page.locator("#login-form input[name=login]").fill("ana.reyes@scholarsync.test")
    staff_page.locator("#login-form input[name=password]").fill(NEW_PASSWORD)
    staff_page.get_by_role("button", name="Log in").click()
    expect(staff_page).to_have_url(f"{base}/staff/")

    office_page.get_by_label("Program (required)").select_option(label="TCU CEAA")
    office_page.get_by_role("button", name="Add to program").click()
    confirm_password_if_asked(office_page)
    expect(office_page.get_by_text("Added to TCU CEAA.")).to_be_visible()
    assert ProgramMembership.objects.filter(program=program).count() == 1

    staff_page.goto(f"{base}/staff/")
    expect(staff_page).to_have_url(f"{base}/staff/tcu-ceaa/")


def test_head_changes_rules_and_staff_cannot(page: Page, live_server, vite_build):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    head = MembershipFactory.create(
        program=program, level=ProgramMembership.Level.HEAD, user__verified=True
    ).user
    staff = MembershipFactory.create(program=program, user__verified=True).user
    base = live_server.url
    log_in(page, base, head.email, "/staff/tcu-ceaa/")
    page.get_by_role("link", name="Settings").click()
    page.get_by_label("Fewest units", exact=True).fill("12")
    page.get_by_role("button", name="Save rules").click()
    expect(page.get_by_text("Rules saved.")).to_be_visible()

    page.context.clear_cookies()
    log_in(page, base, staff.email, "/staff/tcu-ceaa/")
    expect(page.get_by_role("link", name="Settings")).to_have_count(0)
    response = page.goto(f"{base}/staff/tcu-ceaa/settings/")
    assert response is not None and response.status == 403


@pytest.mark.parametrize("section", ["", "tiers/", "documents/"])
def test_settings_pages_have_one_h1_and_no_horizontal_scroll(
    page: Page, live_server, vite_build, section: str
):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    term = AcademicTermFactory.create(is_current=True)
    BenefitTierFactory.create(program=program, effective_from=term)
    RequiredDocumentFactory.create(program=program)
    log_in(page, live_server.url, _office().email, f"/staff/tcu-ceaa/settings/{section}")
    expect(page.locator("h1")).to_have_count(1)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
