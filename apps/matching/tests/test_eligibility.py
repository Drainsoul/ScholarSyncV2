from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.matching.eligibility import (
    Academic,
    Check,
    CheckState,
    EligibilityResult,
    evaluate,
)
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.rules import rule_sentence, rule_sentences
from apps.students.barangays import OUTSIDE_TAGUIG
from apps.students.models import StudentProfile

TODAY = date(2026, 11, 10)
TERM = AcademicTerm(starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 20))
EDU = "students:profile-education"
PERSONAL = "students:profile-personal"


def make_program(**overrides: Any) -> Program:
    values: dict[str, Any] = {
        "slug": "ceaa",
        "name": "CEAA",
        "min_gwa_percent": Decimal("80.00"),
        "max_gwa_one_to_five": Decimal("2.00"),
        "merit_min_gwa_percent": Decimal("90.00"),
        "min_units": 15,
        "min_residency_years": 3,
        "requires_registered_voter": True,
        "allowed_school_types": ["suc", "lcu"],
        "applications_open_on": date(2026, 10, 1),
        "applications_close_on": date(2026, 12, 31),
    }
    values.update(overrides)
    return Program(**values)


def make_profile(**overrides: Any) -> StudentProfile:
    values: dict[str, Any] = {
        "barangay": "ususan",
        "residing_since": 2015,
        "is_registered_voter": True,
    }
    values.update(overrides)
    return StudentProfile(**values)


def make_academic(**overrides: Any) -> Academic:
    values: dict[str, Any] = {
        "school": None,
        "school_name": "TUP Taguig",
        "school_type": "suc",
        "gwa_scale": "percent",
        "gwa": Decimal("88.50"),
        "units": 18,
        "course": "BSIT",
        "year_level": 2,
    }
    values.update(overrides)
    return Academic(**values)


def run(
    program: Program | None = None,
    profile: StudentProfile | None = None,
    academic: Academic | None = None,
    *,
    today: date = TODAY,
    term: AcademicTerm | None = TERM,
    tiers: tuple[BenefitTier, ...] = (),
    allowed_schools: tuple[School, ...] = (),
    no_academic: bool = False,
) -> EligibilityResult:
    return evaluate(
        profile or make_profile(),
        program or make_program(),
        None if no_academic else (academic or make_academic()),
        today=today,
        term=term,
        tiers=tiers,
        allowed_schools=allowed_schools,
    )


def check(result: EligibilityResult, code: str) -> Check:
    return next(c for c in result.checks if c.code == code)


def test_all_rules_met_is_eligible_with_tiers() -> None:
    tiers = (BenefitTier(code="a", name="A"), BenefitTier(code="b", name="B"))
    result = run(tiers=tiers)
    assert result.eligible
    assert [c.state for c in result.checks] == [CheckState.MET] * len(result.checks)
    assert result.tier_candidates == tiers
    assert result.reasons == []


@pytest.mark.django_db
def test_evaluate_makes_no_queries(django_assert_num_queries: Any) -> None:
    school = School(name="X", type="suc", grading_scale="percent")
    with django_assert_num_queries(0):
        run(
            make_program(),
            academic=make_academic(school=school),
            allowed_schools=(school,),
        )


def test_window_no_term() -> None:
    c = check(run(term=None), "window")
    assert c.state == CheckState.UNMET
    assert c.reason == (
        "Applications aren't open: the scholarship office hasn't set up the current school term."
    )


def test_window_not_yet_open() -> None:
    c = check(run(today=date(2026, 9, 30)), "window")
    assert c.state == CheckState.UNMET
    assert c.reason == "Applications open on 1 October 2026."
    assert c.fix_url_name == ""


def test_window_closed() -> None:
    c = check(run(today=date(2027, 1, 1)), "window")
    assert c.state == CheckState.UNMET
    assert c.reason == "Applications closed on 31 December 2026."


def test_school_missing() -> None:
    c = check(run(no_academic=True), "school")
    assert c.state == CheckState.MISSING
    assert c.reason == "Add your current school to your profile."
    assert c.fix_url_name == EDU


def test_allowed_schools_unmet() -> None:
    a = School(name="TUP", type="suc", grading_scale="percent")
    b = School(name="PLM", type="suc", grading_scale="percent")
    program = make_program(allowed_school_types=[])
    result = run(program, academic=make_academic(school=None), allowed_schools=(a, b))
    c = check(result, "allowed_schools")
    assert c.state == CheckState.UNMET
    assert c.reason == "This program is only for students of TUP or PLM."
    assert c.text == "Studying at TUP or PLM."


def test_allowed_schools_met_for_listed_school() -> None:
    a = School(name="TUP", type="suc", grading_scale="percent")
    result = run(academic=make_academic(school=a), allowed_schools=(a,))
    assert check(result, "allowed_schools").state == CheckState.MET


def test_school_type_missing() -> None:
    c = check(run(academic=make_academic(school_type="")), "school_type")
    assert c.state == CheckState.MISSING
    assert c.reason == "Add your school's type to your profile."
    assert c.fix_url_name == EDU


def test_school_type_unmet() -> None:
    c = check(run(academic=make_academic(school_type="private")), "school_type")
    assert c.state == CheckState.UNMET
    assert c.reason == (
        "This program is only for state university or college or local college or "
        "university schools."
    )


def test_units_missing() -> None:
    c = check(run(academic=make_academic(units=None)), "units")
    assert c.state == CheckState.MISSING
    assert c.reason == "Add your units this term to your profile."
    assert c.fix_url_name == EDU


def test_units_unmet() -> None:
    c = check(run(academic=make_academic(units=12)), "units")
    assert c.state == CheckState.UNMET
    assert c.reason == "You have 12 units; this program needs at least 15."


def test_gwa_missing() -> None:
    c = check(run(academic=make_academic(gwa=None)), "gwa")
    assert c.state == CheckState.MISSING
    assert c.reason == "Add your GWA and grading scale to your profile."
    assert c.fix_url_name == EDU


def test_gwa_no_rule_for_four_point() -> None:
    c = check(run(academic=make_academic(gwa_scale="four_point", gwa=Decimal("3.50"))), "gwa")
    assert c.state == CheckState.UNMET
    assert c.reason == (
        "This program has no grade rule yet for schools that grade on a 4.00 point scale. "
        "Ask the scholarship office."
    )


def test_gwa_no_rule_for_one_to_five_when_only_percent() -> None:
    program = make_program(max_gwa_one_to_five=None)
    c = check(
        run(program, academic=make_academic(gwa_scale="one_to_five", gwa=Decimal("1.50"))),
        "gwa",
    )
    assert c.reason.endswith("grade on a 1.00 to 5.00 scale. Ask the scholarship office.")


def test_gwa_percent_unmet() -> None:
    c = check(run(academic=make_academic(gwa=Decimal("78.50"))), "gwa")
    assert c.state == CheckState.UNMET
    assert c.reason == "Your GWA of 78.50 doesn't meet this program's minimum of 80%."


def test_gwa_one_to_five_unmet_and_text() -> None:
    c = check(run(academic=make_academic(gwa_scale="one_to_five", gwa=Decimal("3.25"))), "gwa")
    assert c.reason == "Your GWA of 3.25 doesn't meet this program's maximum of 2.00."
    assert c.text == (
        "A GWA of at least 80% (schools that grade in percent). "
        "A GWA of 2.00 or better (schools that grade 1 to 5)."
    )


def test_gwa_one_to_five_lower_is_better() -> None:
    program = make_program(max_gwa_one_to_five=Decimal("3.00"))
    ok = run(program, academic=make_academic(gwa_scale="one_to_five", gwa=Decimal("2.75")))
    bad = run(program, academic=make_academic(gwa_scale="one_to_five", gwa=Decimal("3.25")))
    assert check(ok, "gwa").state == CheckState.MET
    assert check(bad, "gwa").state == CheckState.UNMET


def test_gwa_boundaries_inclusive() -> None:
    program = make_program(max_gwa_one_to_five=Decimal("3.00"))
    pct = run(program, academic=make_academic(gwa=Decimal("80.00")))
    low = run(program, academic=make_academic(gwa_scale="one_to_five", gwa=Decimal("3.00")))
    assert check(pct, "gwa").state == CheckState.MET
    assert check(low, "gwa").state == CheckState.MET


def test_program_without_gwa_rule_passes_any_scale() -> None:
    program = make_program(min_gwa_percent=None, max_gwa_one_to_five=None)
    result = run(program, academic=make_academic(gwa_scale="four_point", gwa=Decimal("2.00")))
    assert "gwa" not in [c.code for c in result.checks]
    assert result.eligible


def test_residency_missing() -> None:
    c = check(run(profile=make_profile(residing_since=None)), "residency")
    assert c.state == CheckState.MISSING
    assert c.reason == "Add the year you started living in Taguig to your profile."
    assert c.fix_url_name == PERSONAL


def test_residency_outside() -> None:
    c = check(run(profile=make_profile(barangay=OUTSIDE_TAGUIG, residing_since=None)), "residency")
    assert c.state == CheckState.UNMET
    assert c.reason == "This program is for students who live in Taguig."


def test_residency_years() -> None:
    c = check(run(profile=make_profile(residing_since=2024)), "residency")
    assert c.state == CheckState.UNMET
    assert c.reason == (
        "This program needs at least 3 years in Taguig; your profile says since 2024."
    )
    assert check(run(profile=make_profile(residing_since=2023)), "residency").state == (
        CheckState.MET
    )


def test_voter_missing_and_unmet() -> None:
    missing = check(run(profile=make_profile(is_registered_voter=None)), "voter")
    assert missing.state == CheckState.MISSING
    assert missing.reason == "Say whether you are a registered voter in your profile."
    assert missing.fix_url_name == PERSONAL
    unmet = check(run(profile=make_profile(is_registered_voter=False)), "voter")
    assert unmet.state == CheckState.UNMET
    assert unmet.reason == "This program is for registered voters of Taguig."


def test_missing_blocks_eligibility_and_tiers_are_empty() -> None:
    tiers = (BenefitTier(code="a", name="A"),)
    result = run(profile=make_profile(is_registered_voter=None), tiers=tiers)
    assert not result.eligible
    assert result.tier_candidates == ()


def test_reasons_in_check_order() -> None:
    result = run(
        profile=make_profile(is_registered_voter=False),
        academic=make_academic(units=10, gwa=Decimal("70.00")),
        term=None,
    )
    assert [c.code for c in result.checks if c.reason] == ["window", "units", "gwa", "voter"]
    assert len(result.reasons) == 4
    assert result.reasons[0].startswith("Applications aren't open")
    assert result.reasons[-1].startswith("This program is for registered voters")


def test_merit_likely_none_without_merit_rule() -> None:
    program = make_program(merit_min_gwa_percent=None)
    assert run(program).merit_likely is None
    assert run(academic=make_academic(gwa=None)).merit_likely is None


def test_merit_likely_true_and_false() -> None:
    assert run(academic=make_academic(gwa=Decimal("91.00"))).merit_likely is True
    assert run(academic=make_academic(gwa=Decimal("88.50"))).merit_likely is False


def test_unlisted_school_fails_allowed_schools_but_passes_type() -> None:
    allowed = School(name="TUP", type="lcu", grading_scale="percent")
    program = make_program(allowed_school_types=["lcu"])
    academic = make_academic(school=None, school_name="Pateros Tech", school_type="lcu")
    result = run(program, academic=academic, allowed_schools=(allowed,))
    assert check(result, "allowed_schools").state == CheckState.UNMET
    assert check(result, "school_type").state == CheckState.MET


@pytest.mark.django_db
def test_rule_sentences_unchanged() -> None:
    program = make_program(
        min_gwa_percent=Decimal("80.00"),
        max_gwa_one_to_five=Decimal("2.00"),
        min_residency_years=1,
        allowed_school_types=["suc"],
    )
    program.save()
    assert rule_sentences(program) == [
        "A GWA of at least 80% (schools that grade in percent).",
        "A GWA of 2.00 or better (schools that grade 1 to 5).",
        "At least 15 units this term.",
        "Living in Taguig for at least 1 year.",
        "A registered voter of Taguig.",
        "Studying at a state university or college school.",
    ]


def test_window_rule_sentence() -> None:
    """Neutral: the same text sits on a met row and next to "Applications closed on ..."."""
    assert rule_sentence(make_program(applications_close_on=None), "window") == (
        "Applications must be open."
    )
    assert rule_sentence(make_program(), "window") == (
        "Applications must be open (they close on 31 December 2026)."
    )


@pytest.mark.django_db
def test_from_record_uses_listed_school() -> None:
    from apps.programs.tests.factories import SchoolFactory
    from apps.students.tests.factories import EducationRecordFactory

    school = SchoolFactory.create(type="suc", grading_scale="one_to_five")
    record = EducationRecordFactory.create(
        school=school, school_name="", gwa_scale="", school_type=""
    )
    academic = Academic.from_record(record)
    assert academic.school == school
    assert academic.school_name == school.name
    assert academic.school_type == "suc"
    assert academic.gwa_scale == "one_to_five"


def test_no_academic_reasons_are_not_repeated() -> None:
    allowed = School(name="TUP", type="suc", grading_scale="percent")
    result = run(make_program(), no_academic=True, allowed_schools=(allowed,))
    assert result.reasons == [
        "Add your current school to your profile.",
        "Add your school's type to your profile.",
        "Add your units this term to your profile.",
        "Add your GWA and grading scale to your profile.",
    ]
