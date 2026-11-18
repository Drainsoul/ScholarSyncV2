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
    evaluate_renewal,
)
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.rules import renewal_rule_sentences, rule_sentence, rule_sentences
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
        "This program is only for students at a state university or college or local college "
        "or university."
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
        "Studying at a state university or college.",
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


@pytest.mark.django_db
def test_academic_from_application_listed_school() -> None:
    from apps.applications.tests.factories import ApplicationFactory
    from apps.programs.tests.factories import SchoolFactory

    school = SchoolFactory.create(type=School.Type.PUBLIC, grading_scale=School.Scale.PERCENT)
    application = ApplicationFactory.create(school=school, school_type="", gwa_scale="")
    academic = Academic.from_application(application)
    assert academic is not None
    assert academic.school == school
    assert academic.school_name == school.name
    assert academic.school_type == "public"
    assert academic.gwa_scale == "percent"


@pytest.mark.django_db
def test_academic_from_application_typed_school() -> None:
    from apps.applications.tests.factories import ApplicationFactory

    application = ApplicationFactory.create(
        school_name="Typed College",
        school_type=School.Type.PRIVATE,
        gwa_scale=School.Scale.ONE_TO_FIVE,
        gwa=Decimal("1.75"),
        units=21,
        course="BSIT",
        year_level=2,
    )
    academic = Academic.from_application(application)
    assert academic == Academic(
        school=None,
        school_name="Typed College",
        school_type="private",
        gwa_scale="one_to_five",
        gwa=Decimal("1.75"),
        units=21,
        course="BSIT",
        year_level=2,
    )


@pytest.mark.django_db
def test_academic_from_application_none_without_school() -> None:
    from apps.applications.tests.factories import ApplicationFactory

    assert Academic.from_application(ApplicationFactory.create()) is None


# --- Renewal rules (M9) ---


def renewal_program(**overrides: Any) -> Program:
    values: dict[str, Any] = {
        "renewal_min_gwa_percent": Decimal("80"),
        "renewal_max_gwa_one_to_five": None,
        "renewal_min_units": 15,
        "renewal_no_failing_grades": False,
    }
    values.update(overrides)
    return make_program(**values)


def renew(
    program: Program,
    academic: Academic | None = None,
    *,
    declares: bool | None = None,
    term: AcademicTerm | None = TERM,
) -> EligibilityResult:
    return evaluate_renewal(
        program,
        academic or make_academic(),
        today=TODAY,
        term=term,
        declares_no_failing=declares,
    )


def check_of(result: EligibilityResult, code: str) -> Check:
    return next(check for check in result.checks if check.code == code)


def test_renewal_percent_pass_and_fail() -> None:
    program = renewal_program()
    assert renew(program, make_academic(gwa=Decimal("80"))).eligible
    result = renew(program, make_academic(gwa=Decimal("79.99")))
    assert not result.eligible
    gwa = check_of(result, "renewal_gwa")
    assert gwa.state == CheckState.UNMET
    assert gwa.reason == "Your GWA of 79.99 doesn't meet this program's renewal minimum of 80%."


def test_renewal_one_to_five_pass_and_fail() -> None:
    program = renewal_program(
        renewal_min_gwa_percent=None, renewal_max_gwa_one_to_five=Decimal("2.50")
    )
    assert renew(program, make_academic(gwa_scale="one_to_five", gwa=Decimal("2.50"))).eligible
    result = renew(program, make_academic(gwa_scale="one_to_five", gwa=Decimal("2.51")))
    assert check_of(result, "renewal_gwa").reason == (
        "Your GWA of 2.51 doesn't meet this program's renewal maximum of 2.50."
    )


def test_renewal_scale_without_rule_is_unmet() -> None:
    result = renew(renewal_program(), make_academic(gwa_scale="four_point", gwa=Decimal("3.5")))
    gwa = check_of(result, "renewal_gwa")
    assert gwa.state == CheckState.UNMET
    assert "no grade rule yet for schools that grade on a 4.00 point scale" in gwa.reason


def test_renewal_gwa_missing() -> None:
    gwa = check_of(renew(renewal_program(), make_academic(gwa=None)), "renewal_gwa")
    assert gwa.state == CheckState.MISSING
    assert gwa.reason == "Add your GWA and grading scale to your profile."


def test_renewal_units_unmet_and_missing() -> None:
    units = check_of(renew(renewal_program(), make_academic(units=12)), "renewal_units")
    assert units.state == CheckState.UNMET
    assert units.reason == "You have 12 units; renewing needs at least 15."
    missing = check_of(renew(renewal_program(), make_academic(units=None)), "renewal_units")
    assert missing.state == CheckState.MISSING
    assert missing.reason == "Add your units this term to your profile."


def test_renewal_skips_new_applicant_rules() -> None:
    program = renewal_program()  # make_program sets residency, voter and school types
    codes = [check.code for check in renew(program).checks]
    assert codes == ["window", "school", "renewal_gwa", "renewal_units"]


def test_renewal_without_rules_checks_window_and_school() -> None:
    program = renewal_program(renewal_min_gwa_percent=None, renewal_min_units=None)
    assert [check.code for check in renew(program).checks] == ["window", "school"]


NO_FAILING_MISSING = "Confirm below that you have no failing, incomplete or dropped subjects."
NO_FAILING_UNMET = (
    "Renewing needs no failing, incomplete or dropped subjects this term. "
    "Contact the scholarship office."
)


@pytest.mark.parametrize(
    ("declares", "state", "reason"),
    [
        (None, CheckState.MISSING, NO_FAILING_MISSING),
        (False, CheckState.UNMET, NO_FAILING_UNMET),
        (True, CheckState.MET, ""),
    ],
)
def test_no_failing_states(declares: bool | None, state: CheckState, reason: str) -> None:
    program = renewal_program(renewal_no_failing_grades=True)
    check = check_of(renew(program, declares=declares), "no_failing")
    assert (check.state, check.reason) == (state, reason)


def test_no_failing_absent_when_rule_off() -> None:
    codes = [check.code for check in renew(renewal_program(), declares=False).checks]
    assert "no_failing" not in codes


def test_renewal_has_no_tier_candidates_and_proposes_merit() -> None:
    result = renew(renewal_program(), make_academic(gwa=Decimal("95")))
    assert result.eligible
    assert result.tier_candidates == ()
    assert result.merit_likely is True


def test_renewal_window_without_term() -> None:
    assert check_of(renew(renewal_program(), term=None), "window").state == CheckState.UNMET


def test_renewal_school_missing() -> None:
    result = evaluate_renewal(
        renewal_program(), None, today=TODAY, term=TERM, declares_no_failing=None
    )
    assert check_of(result, "school").state == CheckState.MISSING


def test_renewal_rule_sentences() -> None:
    program = renewal_program(
        renewal_max_gwa_one_to_five=Decimal("2.50"), renewal_no_failing_grades=True
    )
    assert renewal_rule_sentences(program) == [
        "To renew: a GWA of at least 80% (schools that grade in percent). "
        "To renew: a GWA of 2.50 or better (schools that grade 1 to 5).",
        "To renew: at least 15 units this term.",
        "To renew: no failing, incomplete or dropped subjects this term.",
    ]
    bare = renewal_program(renewal_min_gwa_percent=None, renewal_min_units=None)
    assert renewal_rule_sentences(bare) == []
