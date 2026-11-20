from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.money.models import Disbursement
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.programs.models import Program
from apps.programs.selectors import renewal_rule_text
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.dashboard import student_dashboard
from apps.students.tests.factories import ProfileFactory
from apps.workspace.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
S = Application.Status


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


def _home(client: Any, user: User) -> str:
    client.force_login(user)
    response = client.get(reverse("students:home"))
    assert response.status_code == 200
    return str(response.content.decode())


def test_renewal_rule_text_for_seeded_programs() -> None:
    ceaa = Program(renewal_min_gwa_percent=Decimal("80.00"), renewal_min_units=15)
    assert renewal_rule_text(ceaa) == "keep a GWA of 80% or better with at least 15 units."
    lani = Program(
        renewal_max_gwa_one_to_five=Decimal("2.50"),
        renewal_min_units=15,
        renewal_no_failing_grades=True,
    )
    assert renewal_rule_text(lani) == (
        "keep a GWA of 2.5 or better on the 1–5 scale with at least 15 units and no failing grades."
    )
    both = Program(
        renewal_min_gwa_percent=Decimal("85"), renewal_max_gwa_one_to_five=Decimal("2.25")
    )
    assert renewal_rule_text(both) == (
        "keep a GWA of 85% or better or a GWA of 2.25 or better on the 1–5 scale."
    )
    assert renewal_rule_text(Program(renewal_min_units=12)) == "keep at least 12 units."
    assert renewal_rule_text(Program()) == ""


def test_returned_banner_shows_reason_escaped_and_skips_on_behalf(client: Any) -> None:
    profile = ProfileFactory.create()
    mine = ApplicationFactory.create(
        profile=profile, status=S.RETURNED, submitted_at=NOW, decision_reason="<b>Blurry</b> slip"
    )
    behalf = ProgramFactory.create(name="Staff Filed")
    ApplicationFactory.create(
        profile=profile,
        program=behalf,
        status=S.RETURNED,
        submitted_at=NOW,
        on_behalf=True,
        created_by=MembershipFactory.create(program=behalf).user,
    )
    assert profile.user is not None
    html = _home(client, profile.user)
    assert f"{mine.program.name} returned your application" in html
    assert "&lt;b&gt;Blurry&lt;/b&gt; slip" in html
    assert "Staff Filed returned your application" not in html
    assert reverse("applications:detail", args=[mine.pk]) in html
    assert "Fix application" in html


def test_award_card_amount_uses_confirmed_merit_and_next_release() -> None:
    profile = ProfileFactory.create()
    program = ProgramFactory.create(renewal_min_gwa_percent=Decimal("80"), renewal_min_units=15)
    term = AcademicTermFactory.create(is_current=True)
    tier = BenefitTierFactory.create(
        program=program,
        name="Honors",
        base_amount=Decimal("5000.00"),
        merit_amount=Decimal("10000.00"),
    )
    award = AwardFactory.create(
        source_application__program=program, source_application__profile=profile, tier=tier
    )
    staff = MembershipFactory.create(program=program).user
    ScholarTermFactory.create(
        award=award, term=term, tier=tier, merit=True, merit_confirmed_by=staff
    )
    ScheduleFactory.create(program=program, term=term, distribution_date=TODAY + timedelta(9))
    assert profile.user is not None
    board = student_dashboard(profile.user, today=TODAY)
    (card,) = board.awards
    assert (card.program_name, card.status_label, card.tier_name) == (
        program.name,
        "Active",
        "Honors",
    )
    assert card.amount == Decimal("10000.00")
    assert card.next_release == date(2026, 11, 26)
    assert card.renew_text == "keep a GWA of 80% or better with at least 15 units."


def test_award_without_term_record_uses_tier_base_and_no_release() -> None:
    profile = ProfileFactory.create()
    tier = BenefitTierFactory.create(base_amount=Decimal("7500.00"))
    AwardFactory.create(
        source_application__program=tier.program, source_application__profile=profile, tier=tier
    )
    assert profile.user is not None
    (card,) = student_dashboard(profile.user, today=TODAY).awards
    assert (card.amount, card.next_release, card.renew_text) == (Decimal("7500.00"), None, "")


def test_graduated_award_has_no_card() -> None:
    profile = ProfileFactory.create()
    AwardFactory.create(source_application__profile=profile, status=Award.Status.GRADUATED)
    suspended = AwardFactory.create(
        source_application__profile=profile, status=Award.Status.SUSPENDED
    )
    assert profile.user is not None
    cards = student_dashboard(profile.user, today=TODAY).awards
    assert [card.program_name for card in cards] == [suspended.program.name]
    assert cards[0].status_label == suspended.get_status_display()


def test_applications_allowances_and_notices_limited_and_ordered(client: Any) -> None:
    profile = ProfileFactory.create()
    assert profile.user is not None
    award = AwardFactory.create(source_application__profile=profile)
    for _n in range(7):
        ApplicationFactory.create(profile=profile)
    newest = ApplicationFactory.create(
        profile=profile, status=S.SUBMITTED, submitted_at=NOW, first_submitted_at=NOW
    )
    for n in range(4):
        term = AcademicTermFactory.create(school_year_start=2020 + n)
        record = ScholarTermFactory.create(award=award, term=term)
        schedule = ScheduleFactory.create(program=award.program, term=term)
        DisbursementFactory.create(
            scholar_term=record, schedule=schedule, status=Disbursement.Status.RELEASED
        )
    for n in range(5):
        NotificationFactory.create(recipient=profile.user, title=f"Notice {n}")
    board = student_dashboard(profile.user, today=TODAY)
    assert len(board.applications) == 5
    assert board.applications[0]["application"] == newest
    assert board.applications[0]["submitted"] == "17 Nov 2026"
    assert board.applications[1]["submitted"] == "Not sent yet"
    assert [row["term"] for row in board.allowances] == [
        "1st semester, SY 2023–2024",
        "1st semester, SY 2022–2023",
        "1st semester, SY 2021–2022",
    ]
    assert {(row["label"], row["tone"]) for row in board.allowances} == {("Received", "success")}
    assert len(board.notices) == 3
    html = _home(client, profile.user)
    assert "Notice 4" in html and "Notice 1" not in html


def test_empty_student_sees_empty_states(client: Any) -> None:
    profile = ProfileFactory.create()
    assert profile.user is not None
    html = _home(client, profile.user)
    for text in ("You haven't applied yet.", "No allowances yet.", "No notifications yet."):
        assert text in html
    assert reverse("matching:match") in html
    assert 'href="#"' not in html


def test_home_greets_the_student_instead_of_naming_another_page(client: Any) -> None:
    profile = ProfileFactory.create(user__full_name="Carolyn Hawkins")
    assert profile.user is not None
    html = _home(client, profile.user)
    assert "<title>Home" in html
    assert "<h1>Good afternoon, Carolyn</h1>" in html
    assert "Your scholarships" not in html


def test_next_section_line_for_an_incomplete_profile(client: Any) -> None:
    profile = ProfileFactory.create()
    assert profile.user is not None
    assert "Next: " in _home(client, profile.user)


def test_staff_cannot_open_student_home(client: Any) -> None:
    client.force_login(MembershipFactory.create().user)
    assert client.get(reverse("students:home")).status_code == 403


def test_home_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    # Rev 26's calendar runs the Find scholarships check: a current term and several programs
    # must not add queries per program (measured 35 with 0 or 8 extra programs).
    AcademicTermFactory.create(school_year_start=2026, is_current=True)
    ProgramFactory.create_batch(8)
    profile = ProfileFactory.create()
    assert profile.user is not None
    for _ in range(3):
        award = AwardFactory.create(source_application__profile=profile)
        for _n in range(7):
            term = AcademicTermFactory.create()
            record = ScholarTermFactory.create(award=award, term=term)
            schedule = ScheduleFactory.create(program=award.program, term=term)
            DisbursementFactory.create(scholar_term=record, schedule=schedule)
    ApplicationFactory.create_batch(10, profile=profile)
    NotificationFactory.create_batch(20, recipient=profile.user)
    client.force_login(profile.user)
    with django_assert_max_num_queries(40):
        assert client.get(reverse("students:home")).status_code == 200
