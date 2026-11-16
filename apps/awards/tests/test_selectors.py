from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.awards.selectors import (
    RenewalStatus,
    at_risk_q,
    at_risk_reasons,
    holds_award,
    other_active_awards,
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


def test_other_active_awards_excludes_this_program_and_inactive() -> None:
    here = AwardFactory.create()
    other = AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(),
    )
    AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(),
        status=Award.Status.INACTIVE,
    )
    assert other_active_awards(here.profile, here.program) == [other]


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


# --- At risk ---

TODAY = date(2026, 10, 15)


def _risk_world(
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


def _flagged(program: Program, term: AcademicTerm | None) -> set[int]:
    rows = with_latest_term(Award.objects.filter(program=program))
    return set(rows.filter(at_risk_q(program, term, TODAY)).values_list("pk", flat=True))


def _reasons(award: Award, term: AcademicTerm | None) -> list[str]:
    annotated = with_latest_term(Award.objects.filter(pk=award.pk)).get()
    return at_risk_reasons(annotated, award.program, term, TODAY)


def test_at_risk_gwa_percent_and_one_to_five() -> None:
    program, tier, previous, current = _risk_world()
    low = make_scholar(program, tier, [previous], gwa=Decimal("79.50"))
    ok = make_scholar(program, tier, [previous], gwa=Decimal("80"))
    low_15 = make_scholar(program, tier, [previous], gwa=Decimal("2.75"), gwa_scale="one_to_five")
    ok_15 = make_scholar(program, tier, [previous], gwa=Decimal("2.50"), gwa_scale="one_to_five")
    assert _flagged(program, current) == {low.pk, low_15.pk}
    assert _reasons(low, current) == ["Last term's GWA of 79.50 misses the renewal mark."]
    assert _reasons(ok, current) == []
    assert ok_15.pk not in _flagged(program, current)


def test_at_risk_units() -> None:
    program, tier, previous, current = _risk_world()
    few = make_scholar(program, tier, [previous], units=12)
    assert _flagged(program, current) == {few.pk}
    assert _reasons(few, current) == ["Last term's 12 units are under the renewal minimum."]


def test_at_risk_not_renewed_after_close() -> None:
    program, tier, previous, current = _risk_world(applications_close_on=date(2026, 10, 1))
    unrenewed = make_scholar(program, tier, [previous])
    renewed = make_scholar(program, tier, [previous, current])
    assert _flagged(program, current) == {unrenewed.pk}
    assert _reasons(unrenewed, current) == ["Not renewed, and renewals have closed."]
    assert _reasons(renewed, current) == []


def test_not_at_risk_when_window_open_and_unrenewed() -> None:
    program, tier, previous, current = _risk_world()
    make_scholar(program, tier, [previous])
    assert _flagged(program, current) == set()


def test_scale_without_rule_not_flagged() -> None:
    program, tier, previous, current = _risk_world(renewal_max_gwa_one_to_five=None)
    award = make_scholar(program, tier, [previous], gwa=Decimal("4.50"), gwa_scale="one_to_five")
    four = make_scholar(program, tier, [previous], gwa=Decimal("1.00"), gwa_scale="four_point")
    assert _flagged(program, current) == set()
    assert _reasons(award, current) == [] and _reasons(four, current) == []


def test_suspended_never_at_risk() -> None:
    program, tier, previous, current = _risk_world(applications_close_on=date(2026, 10, 1))
    award = make_scholar(
        program, tier, [previous], gwa=Decimal("60"), status=Award.Status.SUSPENDED
    )
    assert _flagged(program, current) == set()
    assert _reasons(award, current) == []


def test_summer_not_at_risk_for_renewal() -> None:
    program, tier, previous, current = _risk_world(3, applications_close_on=date(2026, 10, 1))
    award = make_scholar(program, tier, [previous])
    assert _flagged(program, current) == set()
    assert _reasons(award, current) == []


def test_no_rules_nothing_flagged() -> None:
    program, tier, previous, current = _risk_world(
        renewal_min_gwa_percent=None, renewal_max_gwa_one_to_five=None, renewal_min_units=None
    )
    make_scholar(program, tier, [previous], gwa=Decimal("50"), units=3)
    assert _flagged(program, current) == set()


def test_at_risk_q_agrees_with_reasons() -> None:
    program, tier, previous, current = _risk_world(applications_close_on=date(2026, 10, 1))
    awards = [
        make_scholar(program, tier, [previous], gwa=Decimal("70")),
        make_scholar(program, tier, [previous, current]),
        make_scholar(program, tier, [previous, current], units=10),
        make_scholar(program, tier, [previous]),
        make_scholar(program, tier, [previous, current], gwa=Decimal("90")),
    ]
    expected = {award.pk for award in awards if _reasons(award, current)}
    assert _flagged(program, current) == expected


def test_with_latest_term_picks_latest_by_sort_key() -> None:
    program, tier, previous, current = _risk_world()
    school = SchoolFactory.create(name="Listed University")
    award = make_scholar(program, tier, [current], gwa=Decimal("90"), units=20)
    add_record(award, previous, gwa=Decimal("70"), units=9, school_name="Old College")
    ScholarTerm.objects.filter(award=award, term=current).update(school=school, school_name="")
    row: Any = with_latest_term(Award.objects.filter(pk=award.pk)).get()
    assert row.latest_term_id == current.pk
    assert (row.latest_gwa, row.latest_units) == (Decimal("90.00"), 20)
    assert row.latest_school_name == "Listed University"
    assert row.term_count == 2
