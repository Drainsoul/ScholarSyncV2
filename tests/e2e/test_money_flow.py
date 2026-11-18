"""Schedules, disbursements, the budget and the student's payouts, end to end (M10)."""

import re
from decimal import Decimal

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.money.models import Budget, Disbursement
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.workspace.models import EmailOutbox
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e

SLUG = "tcu-ceaa"


class World:
    """TCU CEAA with a current term, two scholars ready to be paid, staff and a head."""

    def __init__(self) -> None:
        self.term = AcademicTermFactory.create(is_current=True)
        self.program = ProgramFactory.create(slug=SLUG, name="TCU CEAA")
        self.tier = BenefitTierFactory.create(
            program=self.program, code="standard", name="Standard", effective_from=self.term
        )
        self.staff: User = MembershipFactory.create(program=self.program, user__verified=True).user
        self.head: User = MembershipFactory.create(
            program=self.program, level=ProgramMembership.Level.HEAD, user__verified=True
        ).user

    def scholar(self) -> Award:
        award = AwardFactory.create(
            source_application__program=self.program,
            tier=self.tier,
        )
        ScholarTermFactory.create(
            award=award,
            term=self.term,
            tier=self.tier,
            compliance=ScholarTerm.Compliance.COMPLETE,
        )
        return award


def switch_user(page: Page, base: str, email: str, next_path: str) -> None:
    page.context.clear_cookies()
    log_in(page, base, email, next_path)


def confirm_password(page: Page) -> None:
    expect(page).to_have_url(re.compile(r".*/accounts/reauthenticate/.*"))
    page.locator("input[name=password]").fill(DEFAULT_PASSWORD)
    page.get_by_role("button", name="Confirm").click()


def test_staff_generates_and_head_releases(page: Page, live_server, vite_build, console_errors):
    world = World()
    awards = [world.scholar(), world.scholar()]
    base = live_server.url
    log_in(page, base, world.staff.email, f"/staff/{SLUG}/schedules/new/")

    page.get_by_label("Term").select_option(label=str(world.term))
    page.get_by_label("Distribution day").fill(timezone.localdate().isoformat())
    page.get_by_label("Claim location").fill("TCU Gymnasium")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Schedule saved.")).to_be_visible()
    page.get_by_role("button", name="Publish").click()
    expect(page.get_by_text("Published. Scholars can see this schedule.")).to_be_visible()

    page.get_by_role("link", name="Disbursements").first.click()
    today = timezone.localdate()
    page.get_by_role("link", name=f"{today.day} {today:%B %Y}").click()
    page.get_by_role("button", name="Generate disbursements").click()
    expect(page.get_by_text("Generated 2 disbursements.")).to_be_visible()
    expect(page.get_by_role("button", name="Approve selected")).to_have_count(0)
    schedule_path = page.url.removeprefix(base)

    switch_user(page, base, world.head.email, schedule_path)
    for award in awards:
        page.get_by_label(f"Select {award.profile.full_name}").check()
    page.get_by_role("button", name="Approve selected").click()
    expect(page.get_by_text("Approved 2 payouts.")).to_be_visible()

    for award in awards:
        page.get_by_label(f"Select {award.profile.full_name}").check()
    page.get_by_role("button", name="Release selected").click()
    confirm_password(page)
    expect(page.get_by_text("Released 2 payouts.")).to_be_visible()
    assert set(Disbursement.objects.values_list("status", flat=True)) == {"released"}
    assert EmailOutbox.objects.filter(kind="allowance_released").count() == 2
    assert not console_errors


def test_student_sees_payouts(page: Page, live_server, vite_build, console_errors):
    world = World()
    award = world.scholar()
    record = award.terms.get()
    schedule = ScheduleFactory.create(
        program=world.program, term=world.term, distribution_date=timezone.localdate()
    )
    DisbursementFactory.create(
        scholar_term=record,
        schedule=schedule,
        status=Disbursement.Status.RELEASED,
        released_at=timezone.now(),
    )
    student = award.profile.user
    assert student is not None
    log_in(page, live_server.url, student.email, "/me/scholarships/")
    expect(page.get_by_text("Times claimed")).to_be_visible()
    expect(page.get_by_text("Received", exact=False).first).to_be_visible()
    expect(page.get_by_text("₱5,000.00").first).to_be_visible()
    assert not console_errors


def test_budget_page(page: Page, live_server, vite_build, console_errors):
    world = World()
    base = live_server.url
    year = timezone.localdate().year
    log_in(page, base, world.head.email, f"/staff/{SLUG}/budget/")
    page.get_by_role("link", name="Set budget").click()
    page.get_by_label("Budget (PHP)").fill("1000000")
    page.get_by_role("button", name="Save budget").click()
    confirm_password(page)
    expect(page.get_by_text(f"Budget for {year} saved.")).to_be_visible()
    for label in ("Released", "Approved, not yet released", "Available", "Budget used"):
        expect(page.get_by_text(label, exact=True).first).to_be_visible()
    assert Budget.objects.get().amount == Decimal("1000000.00")
    page.goto(f"{base}/staff/{SLUG}/budget/?year={year + 1}")
    expect(page.get_by_text("No budget set")).to_be_visible()
    assert not console_errors


def test_disbursement_table_bulk_fits_at_375(page: Page, live_server, vite_build):
    world = World()
    schedule = ScheduleFactory.create(program=world.program, term=world.term)
    for _ in range(2):
        award = world.scholar()
        DisbursementFactory.create(
            schedule=schedule, scholar_term=award.terms.get(), amount=Decimal("5000.00")
        )
    page.set_viewport_size({"width": 375, "height": 812})
    log_in(page, live_server.url, world.head.email, f"/staff/{SLUG}/disbursements/{schedule.pk}/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    select_all = page.get_by_label("Select all on this page")
    expect(select_all).to_be_visible()
    select_all.check()
    expect(page.locator("[data-bulk-count]")).to_have_text("2 selected")
