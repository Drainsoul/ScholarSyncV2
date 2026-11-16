"""Scholars, renewals and the term change, end to end (M9)."""

from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.forms import DECLARATION_LABEL
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.scholars import make_scholar
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory
from tests.e2e.flows import log_in, one_kb_pdf, payload

pytestmark = pytest.mark.e2e

SLUG = "tcu-ceaa"


class World:
    """TCU CEAA with renewal rules, last semester and this one, and one staff member."""

    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program: Program = ProgramFactory.create(
            slug=SLUG,
            name="TCU CEAA",
            renewal_min_gwa_percent=Decimal("80"),
            renewal_min_units=15,
        )
        self.tier: BenefitTier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard", name="Standard"
        )
        RequiredDocumentFactory.create(
            program=self.program, code="cor", label="Registration form", applies_to="renewal"
        )
        self.staff: User = MembershipFactory.create(program=self.program, user__verified=True).user

    def scholar(self, first_name: str = "Carmela", **fields: Any) -> Award:
        profile = FullProfileFactory.create(first_name=first_name, user__verified=True)
        EducationRecordFactory.create(
            profile=profile,
            school=None,
            school_name="Taguig City University",
            school_type="lcu",
            gwa=Decimal("88.00"),
            gwa_scale="percent",
            units=21,
            year_level=2,
        )
        return make_scholar(self.program, self.tier, [self.previous], profile=profile, **fields)


def switch_user(page: Page, base: str, email: str, next_path: str) -> None:
    page.context.clear_cookies()
    log_in(page, base, email, next_path)


def test_scholar_renews_and_staff_approves(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    world = World()
    award = world.scholar()
    student = award.profile.user
    assert student is not None
    log_in(page, live_server.url, student.email, "/me/scholarships/")

    page.get_by_role("button", name=f"Renew for {world.current}").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Renewal: TCU CEAA")
    row = page.locator("li[id^=doc-]").first
    upload = payload("registration.pdf", "application/pdf", one_kb_pdf())
    row.locator("input[type=file]").set_input_files(files=upload)
    expect(row.locator(".file-input__status")).to_have_text(f"{upload['name']} uploaded")
    row.get_by_role("button", name="Save document").click()
    expect(page.get_by_text("Document saved.").first).to_be_visible()
    page.get_by_label(DECLARATION_LABEL).check()
    page.get_by_role("button", name="Submit application").click()
    expect(page.get_by_text("Application submitted.").first).to_be_visible()

    switch_user(page, live_server.url, world.staff.email, f"/staff/{SLUG}/applications/")
    page.get_by_label("Kind").select_option("renewal")
    page.get_by_role("button", name="Apply filters").click()
    page.get_by_role("link", name=award.profile.full_name).click()
    expect(page.get_by_text(f"Renewal for {world.current}.").first).to_be_visible()
    page.get_by_role("button", name="Start review").click()
    page.get_by_role("button", name="Approve Registration form").click()
    expect(
        page.get_by_role("row", name="Registration form").get_by_text("Approved")
    ).to_be_visible()
    page.get_by_label("Approve", exact=True).check()
    page.get_by_role("button", name="Save decision").click()
    name = award.profile.full_name
    expect(
        page.get_by_text(
            f"Application approved. {name}'s scholarship is renewed for {world.current}."
        )
    ).to_be_visible()
    assert ScholarTerm.objects.filter(award=award, term=world.current).exists()

    page.get_by_role("link", name="Open the scholar's record").click()
    expect(page.get_by_role("rowheader", name=str(world.current))).to_be_visible()

    switch_user(page, live_server.url, student.email, "/me/scholarships/")
    expect(page.get_by_text(f"Renewed for {world.current}.")).to_be_visible()
    assert console_errors == []


def test_staff_hold_and_reinstate(page: Page, live_server, vite_build, console_errors):
    world = World()
    award = world.scholar("Elena")
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/?scholar={award.pk}")
    expect(page.get_by_role("heading", name="Scholar details")).to_be_visible()
    page.get_by_role("link", name="Open record").click()
    page.get_by_role("link", name="Put on hold").click()
    page.get_by_label("Reason").fill("Waiting for the registrar.")
    page.get_by_role("button", name="Put on hold").click()
    expect(page.get_by_text("Put on hold. The award is now suspended.")).to_be_visible()
    expect(page.get_by_text("Suspended: Waiting for the registrar.")).to_be_visible()
    page.get_by_role("link", name="Reinstate").click()
    page.get_by_role("button", name="Reinstate").click()
    expect(page.get_by_text("Reinstate. The award is now active.")).to_be_visible()
    award.refresh_from_db()
    assert award.status == Award.Status.ACTIVE
    assert console_errors == []


def test_staff_record_term_and_confirm_merit(page: Page, live_server, vite_build, console_errors):
    world = World()
    award = world.scholar("Ramon")
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/{award.pk}/")
    page.get_by_role("link", name="Add a term record").click()
    page.get_by_label("School name").fill("Taguig City University")
    page.get_by_label("School type").select_option("lcu")
    page.get_by_label("Grading scale").select_option("percent")
    page.get_by_label("GWA").fill("91")
    page.get_by_label("Units").fill("21")
    page.get_by_label("Renewal documents checked").check()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Term record added.")).to_be_visible()
    page.get_by_role("button", name="Confirm merit").first.click()
    expect(page.get_by_text("Merit confirmed.")).to_be_visible()
    record = ScholarTerm.objects.get(award=award, term=world.current)
    assert record.compliance == ScholarTerm.Compliance.COMPLETE
    assert ScholarTerm.objects.filter(award=award, merit_confirmed_by=world.staff).exists()
    assert console_errors == []


def test_office_moves_current_term(page: Page, live_server, vite_build, console_errors):
    World()
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    log_in(page, live_server.url, office.email, "/office/terms/")
    page.get_by_role("button", name="Add school year 2027–2028").click()
    expect(page.get_by_text("School year 2027–2028 added.")).to_be_visible()
    target = AcademicTerm.objects.get(school_year_start=2027, term=1)
    page.get_by_role("link", name=f"Make current {target}").click()
    expect(page.get_by_text("0 unfinished applications will be withdrawn.")).to_be_visible()
    page.get_by_role("button", name=f"Make {target} current").click()
    expect(
        page.get_by_text(
            f"{target} is now the current term. Withdrew 0 unfinished applications. "
            "Graduated 0 scholars."
        )
    ).to_be_visible()
    target.refresh_from_db()
    assert target.is_current
    assert console_errors == []


def test_scholars_pages_have_no_console_errors(page: Page, live_server, vite_build, console_errors):
    world = World()
    award = world.scholar()
    base = live_server.url
    log_in(page, base, world.staff.email, f"/staff/{SLUG}/scholars/")
    for path in (
        f"/staff/{SLUG}/scholars/",
        f"/staff/{SLUG}/scholars/?scholar={award.pk}",
        f"/staff/{SLUG}/scholars/{award.pk}/",
        f"/staff/{SLUG}/scholars/{award.pk}/edit/",
    ):
        page.goto(f"{base}{path}")
        expect(page.locator("h1")).to_be_visible()
    student = award.profile.user
    assert student is not None
    switch_user(page, base, student.email, "/me/scholarships/")
    expect(page.get_by_role("heading", level=1)).to_have_text("Your scholarships")
    assert console_errors == []
