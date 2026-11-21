from decimal import Decimal
from typing import Any

import pytest

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.awards.selectors import (
    RenewalStatus,
    held_award_elsewhere,
    holds_award,
    one_scholarship,
    renewal_due_q,
    renewal_for,
    renewal_tier,
    with_latest_term,
)
from apps.awards.tests.factories import AwardFactory, RenewalFactory
from apps.awards.tests.scholars import add_record, make_scholar
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    SchoolFactory,
)

pytestmark = pytest.mark.django_db


def test_holds_award_counts_suspended_not_inactive() -> None:
    award = AwardFactory.create()
    assert holds_award(award.profile, award.program)
    assert not holds_award(award.profile, ProgramFactory.create())
    Award.objects.filter(pk=award.pk).update(status=Award.Status.SUSPENDED)
    assert holds_award(award.profile, award.program)
    for status in (Award.Status.INACTIVE, Award.Status.GRADUATED):
        Award.objects.filter(pk=award.pk).update(status=status)
        assert not holds_award(award.profile, award.program)


def test_held_award_elsewhere_is_active_or_on_hold_in_another_program() -> None:
    here = AwardFactory.create()
    assert held_award_elsewhere(here.profile, here.program) is None
    ended = AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(),
        status=Award.Status.INACTIVE,
    )
    assert held_award_elsewhere(here.profile, here.program) is None
    on_hold = AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(name="LANI"),
        status=Award.Status.SUSPENDED,
    )
    assert held_award_elsewhere(here.profile, here.program) == on_hold
    assert held_award_elsewhere(here.profile, ended.program) in (here, on_hold)
    assert held_award_elsewhere(here.profile, on_hold.program) == here
    assert one_scholarship(on_hold) == (
        "You already hold the LANI scholarship. A student can hold one scholarship at a time."
    )


# --- Renewals (M9) ---


def _renewal_world(term_number: int = 1) -> tuple[Award, AcademicTerm, AcademicTerm]:
    previous = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=term_number, is_current=True)
    program = ProgramFactory.create()
    tier = BenefitTierFactory.create(program=program, effective_from=previous, code="standard")
    return make_scholar(program, tier, [previous]), previous, current


def _renewal(award: Award, term: AcademicTerm, status: str) -> Application:
    return RenewalFactory.create(award=award, term=term, status=status)


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("due", RenewalStatus.DUE),
        ("open", RenewalStatus.OPEN),
        ("renewed", RenewalStatus.RENEWED),
        ("approved", RenewalStatus.RENEWED),
        ("rejected", RenewalStatus.REJECTED),
        ("withdrawn", RenewalStatus.DUE),
        ("summer", RenewalStatus.SUMMER),
        ("no_term", RenewalStatus.NO_TERM),
        ("not_active", RenewalStatus.NOT_ACTIVE),
    ],
)
def test_renewal_for_each_status(setup: str, expected: RenewalStatus) -> None:
    award, _, current = _renewal_world(3 if setup == "summer" else 1)
    term: AcademicTerm | None = current
    application_id = None
    if setup == "open":
        application_id = _renewal(award, current, Application.Status.DRAFT).pk
    elif setup == "renewed":
        add_record(award, current)
    elif setup == "approved":
        _renewal(award, current, Application.Status.APPROVED)
    elif setup == "rejected":
        _renewal(award, current, Application.Status.REJECTED)
    elif setup == "withdrawn":
        _renewal(award, current, Application.Status.WITHDRAWN)
    elif setup == "no_term":
        term = None
    elif setup == "not_active":
        Award.objects.filter(pk=award.pk).update(status=Award.Status.SUSPENDED)
        award.refresh_from_db()
    renewal = renewal_for(award, term)
    assert renewal.status == expected
    assert renewal.term == term
    assert renewal.application_id == application_id


def test_renewal_due_q_matches_renewal_for() -> None:
    due, previous, current = _renewal_world()
    program, tier = due.program, due.tier
    renewed = make_scholar(program, tier, [previous, current])
    open_one = make_scholar(program, tier, [previous])
    _renewal(open_one, current, Application.Status.SUBMITTED)
    rejected = make_scholar(program, tier, [previous])
    _renewal(rejected, current, Application.Status.REJECTED)
    on_hold = make_scholar(program, tier, [previous], status=Award.Status.SUSPENDED)
    awards = [due, renewed, open_one, rejected, on_hold]
    expected = {a.pk for a in awards if renewal_for(a, current).status == RenewalStatus.DUE}
    assert expected == {due.pk}
    assert (
        set(Award.objects.filter(renewal_due_q(current)).values_list("pk", flat=True)) == expected
    )


def test_summer_nobody_due() -> None:
    award, _, current = _renewal_world(3)
    assert renewal_for(award, current).status == RenewalStatus.SUMMER
    assert not Award.objects.filter(renewal_due_q(current)).exists()


def test_renewal_tier_matches_code_after_reprice() -> None:
    award, _, current = _renewal_world()
    repriced = BenefitTierFactory.create(
        program=award.program, effective_from=current, code="standard"
    )
    assert renewal_tier(award, current) == repriced
    assert renewal_tier(award, AcademicTerm.objects.get(school_year_start=2025)) == award.tier


def test_renewal_tier_none_when_code_retired() -> None:
    award, _, current = _renewal_world()
    BenefitTierFactory.create(
        program=award.program, effective_from=current, code="standard", is_active=False
    )
    assert renewal_tier(award, current) is None


# --- Latest term ---


def _scholar_world(
    term_number: int = 1, **program_fields: object
) -> tuple[Program, BenefitTier, AcademicTerm, AcademicTerm]:
    previous = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=term_number, is_current=True)
    values: dict[str, object] = {
        "renewal_min_gwa_percent": Decimal("80"),
        "renewal_max_gwa_one_to_five": Decimal("2.50"),
        "renewal_min_units": 15,
    }
    values.update(program_fields)
    program = ProgramFactory.create(**values)
    tier = BenefitTierFactory.create(program=program, effective_from=previous, code="standard")
    return program, tier, previous, current


def test_with_latest_term_picks_latest_by_sort_key() -> None:
    program, tier, previous, current = _scholar_world()
    school = SchoolFactory.create(name="Listed University")
    award = make_scholar(program, tier, [current], gwa=Decimal("90"), units=20)
    add_record(award, previous, gwa=Decimal("70"), units=9, school_name="Old College")
    ScholarTerm.objects.filter(award=award, term=current).update(school=school, school_name="")
    row: Any = with_latest_term(Award.objects.filter(pk=award.pk)).get()
    assert row.latest_term_id == current.pk
    assert (row.latest_gwa, row.latest_units) == (Decimal("90.00"), 20)
    assert row.latest_school_name == "Listed University"
    assert row.term_count == 2
