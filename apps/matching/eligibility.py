"""Does a student meet a program's rules? Pure: no queries, so callers load everything first."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from django.utils.dateformat import format as format_date

from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.rules import TYPE_WORDS, join_or, rule_sentence
from apps.programs.selectors import window_state
from apps.students.barangays import OUTSIDE_TAGUIG
from apps.students.models import EducationRecord, StudentProfile
from apps.students.selectors import effective_school_type

EDUCATION_FIX = "students:profile-education"
PERSONAL_FIX = "students:profile-personal"
ADD_SCHOOL = "Add your current school to your profile."


class CheckState(StrEnum):
    MET = "met"
    UNMET = "unmet"
    MISSING = "missing"


@dataclass(frozen=True)
class Check:
    code: str
    state: CheckState
    text: str
    reason: str
    fix_url_name: str


@dataclass(frozen=True)
class Academic:
    school: School | None
    school_name: str
    school_type: str
    gwa_scale: str
    gwa: Decimal | None
    units: int | None
    course: str
    year_level: int | None

    @classmethod
    def from_record(cls, record: EducationRecord) -> "Academic":
        school = record.school
        return cls(
            school=school,
            school_name=school.name if school is not None else record.school_name,
            school_type=effective_school_type(record),
            gwa_scale=school.grading_scale if school is not None else record.gwa_scale,
            gwa=record.gwa,
            units=record.units,
            course=record.course,
            year_level=record.year_level,
        )


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    checks: tuple[Check, ...]
    tier_candidates: tuple[BenefitTier, ...]
    merit_likely: bool | None

    @property
    def reasons(self) -> list[str]:
        return [check.reason for check in self.checks if check.reason]


def _date(value: date | None) -> str:
    return format_date(value, "j F Y") if value is not None else ""


def _scale_label(scale: str) -> str:
    return School.Scale(scale).label.split("(")[0].strip().lower()


def _number(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _met(code: str, text: str) -> Check:
    return Check(code, CheckState.MET, text, "", "")


def _threshold(scale: str, percent: Decimal | None, one_to_five: Decimal | None) -> Decimal | None:
    if scale == School.Scale.PERCENT:
        return percent
    if scale == School.Scale.ONE_TO_FIVE:
        return one_to_five
    return None


def _passes(scale: str, gwa: Decimal, limit: Decimal) -> bool:
    return gwa >= limit if scale == School.Scale.PERCENT else gwa <= limit


def _window_check(program: Program, today: date, term: AcademicTerm | None) -> Check:
    text = rule_sentence(program, "window")
    if term is None:
        reason = (
            "Applications aren't open: the scholarship office hasn't set up the current "
            "school term."
        )
    else:
        state = window_state(program, today)
        if state == "open":
            return _met("window", text)
        if state == "not_yet":
            reason = f"Applications open on {_date(program.applications_open_on)}."
        else:
            reason = f"Applications closed on {_date(program.applications_close_on)}."
    return Check("window", CheckState.UNMET, text, reason, "")


def _school_check(academic: Academic | None) -> Check:
    text = "You have a current school in your profile."
    if academic is None or not academic.school_name:
        return Check("school", CheckState.MISSING, text, ADD_SCHOOL, EDUCATION_FIX)
    return _met("school", text)


def _allowed_schools_check(
    program: Program, academic: Academic | None, allowed_schools: Sequence[School]
) -> Check:
    text = rule_sentence(program, "allowed_schools", allowed_schools=allowed_schools)
    if academic is None or not academic.school_name:
        return Check("allowed_schools", CheckState.MISSING, text, ADD_SCHOOL, EDUCATION_FIX)
    if academic.school is not None and academic.school in allowed_schools:
        return _met("allowed_schools", text)
    names = join_or([school.name for school in allowed_schools])
    return Check(
        "allowed_schools",
        CheckState.UNMET,
        text,
        f"This program is only for students of {names}.",
        "",
    )


def _school_type_check(program: Program, academic: Academic | None) -> Check:
    text = rule_sentence(program, "school_type")
    if academic is None or not academic.school_type:
        return Check(
            "school_type",
            CheckState.MISSING,
            text,
            "Add your school's type to your profile.",
            EDUCATION_FIX,
        )
    if academic.school_type in program.allowed_school_types:
        return _met("school_type", text)
    words = join_or([TYPE_WORDS[School.Type(value)] for value in program.allowed_school_types])
    return Check(
        "school_type", CheckState.UNMET, text, f"This program is only for {words} schools.", ""
    )


def _units_check(program: Program, academic: Academic | None) -> Check:
    text = rule_sentence(program, "units")
    minimum = program.min_units
    assert minimum is not None
    if academic is None or academic.units is None:
        return Check(
            "units",
            CheckState.MISSING,
            text,
            "Add your units this term to your profile.",
            EDUCATION_FIX,
        )
    if academic.units >= minimum:
        return _met("units", text)
    return Check(
        "units",
        CheckState.UNMET,
        text,
        f"You have {academic.units} units; this program needs at least {minimum}.",
        "",
    )


def _gwa_check(program: Program, academic: Academic | None) -> Check:
    text = rule_sentence(program, "gwa")
    if academic is None or academic.gwa is None or not academic.gwa_scale:
        return Check(
            "gwa",
            CheckState.MISSING,
            text,
            "Add your GWA and grading scale to your profile.",
            EDUCATION_FIX,
        )
    scale = academic.gwa_scale
    limit = _threshold(scale, program.min_gwa_percent, program.max_gwa_one_to_five)
    if limit is None:
        reason = (
            "This program has no grade rule yet for schools that grade on a "
            f"{_scale_label(scale)} scale. Ask the scholarship office."
        )
        return Check("gwa", CheckState.UNMET, text, reason, "")
    if _passes(scale, academic.gwa, limit):
        return _met("gwa", text)
    if scale == School.Scale.PERCENT:
        sentence = f"minimum of {_number(limit)}%"
    else:
        sentence = f"maximum of {limit}"
    return Check(
        "gwa",
        CheckState.UNMET,
        text,
        f"Your GWA of {academic.gwa} doesn't meet this program's {sentence}.",
        "",
    )


def _residency_check(program: Program, profile: StudentProfile, today: date) -> Check:
    text = rule_sentence(program, "residency")
    years = program.min_residency_years
    assert years is not None
    if profile.barangay == OUTSIDE_TAGUIG:
        return Check(
            "residency",
            CheckState.UNMET,
            text,
            "This program is for students who live in Taguig.",
            "",
        )
    since = profile.residing_since
    if since is None:
        return Check(
            "residency",
            CheckState.MISSING,
            text,
            "Add the year you started living in Taguig to your profile.",
            PERSONAL_FIX,
        )
    if today.year - since >= years:
        return _met("residency", text)
    return Check(
        "residency",
        CheckState.UNMET,
        text,
        f"This program needs at least {years} years in Taguig; your profile says since {since}.",
        "",
    )


def _voter_check(program: Program, profile: StudentProfile) -> Check:
    text = rule_sentence(program, "voter")
    if profile.is_registered_voter is None:
        return Check(
            "voter",
            CheckState.MISSING,
            text,
            "Say whether you are a registered voter in your profile.",
            PERSONAL_FIX,
        )
    if profile.is_registered_voter:
        return _met("voter", text)
    return Check(
        "voter", CheckState.UNMET, text, "This program is for registered voters of Taguig.", ""
    )


def _merit_likely(program: Program, academic: Academic | None) -> bool | None:
    if academic is None or academic.gwa is None or not academic.gwa_scale:
        return None
    limit = _threshold(
        academic.gwa_scale, program.merit_min_gwa_percent, program.merit_max_gwa_one_to_five
    )
    if limit is None:
        return None
    return _passes(academic.gwa_scale, academic.gwa, limit)


def evaluate(
    profile: StudentProfile,
    program: Program,
    academic: Academic | None,
    *,
    today: date,
    term: AcademicTerm | None,
    tiers: Sequence[BenefitTier],
    allowed_schools: Sequence[School],
) -> EligibilityResult:
    checks = [_window_check(program, today, term), _school_check(academic)]
    if allowed_schools:
        checks.append(_allowed_schools_check(program, academic, allowed_schools))
    if program.allowed_school_types:
        checks.append(_school_type_check(program, academic))
    if program.min_units is not None:
        checks.append(_units_check(program, academic))
    if program.min_gwa_percent is not None or program.max_gwa_one_to_five is not None:
        checks.append(_gwa_check(program, academic))
    if program.min_residency_years is not None:
        checks.append(_residency_check(program, profile, today))
    if program.requires_registered_voter:
        checks.append(_voter_check(program, profile))
    eligible = all(check.state == CheckState.MET for check in checks)
    return EligibilityResult(
        eligible=eligible,
        checks=tuple(checks),
        tier_candidates=tuple(tiers) if eligible else (),
        merit_likely=_merit_likely(program, academic),
    )
