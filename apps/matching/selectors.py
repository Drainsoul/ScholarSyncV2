from dataclasses import dataclass, replace
from datetime import date

from django.db.models import Exists, OuterRef, Q, Subquery

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award
from apps.awards.selectors import ONE_SCHOLARSHIP
from apps.matching.eligibility import (
    Academic,
    Check,
    CheckState,
    EligibilityResult,
    evaluate,
    evaluate_renewal,
)
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import application_term, tiers_in_force, tiers_in_force_for
from apps.students.models import StudentProfile
from apps.students.selectors import current_education, profile_for


@dataclass(frozen=True)
class ProgramMatch:
    program: Program
    result: EligibilityResult
    open_application_id: int | None  # the student's open application for this program and term
    held: bool = False  # an approved application this term, or an active award
    rejected: bool = False  # a rejected application this term: no new one until next term
    open_on_behalf: bool = (
        False  # the open application was filed by staff: the student only views it
    )


@dataclass(frozen=True)
class MatchPage:
    profile: StudentProfile | None
    academic: Academic | None
    term: AcademicTerm | None
    matches: list[ProgramMatch]  # active programs, by name


def _academic(profile: StudentProfile) -> Academic | None:
    record = current_education(profile)
    return Academic.from_record(record) if record is not None else None


def _evaluate(
    profile: StudentProfile,
    program: Program,
    academic: Academic | None,
    term: AcademicTerm | None,
    today: date,
    tiers: list[BenefitTier] | None = None,
) -> EligibilityResult:
    if tiers is None:
        tiers = tiers_in_force(program, term) if term is not None else []
    return evaluate(
        profile,
        program,
        academic,
        today=today,
        term=term,
        tiers=tiers,
        allowed_schools=list(program.allowed_schools.all()),
    )


def eligibility_for(profile: StudentProfile, program: Program, *, today: date) -> EligibilityResult:
    """Run the rules for one program, loading what `evaluate` needs (term, tiers, schools)."""
    return eligibility_with(profile, program, _academic(profile), today=today)


def eligibility_with(
    profile: StudentProfile, program: Program, academic: Academic | None, *, today: date
) -> EligibilityResult:
    """`eligibility_for` on school and grades the caller already read (None: no current school)."""
    return _evaluate(profile, program, academic, application_term(today), today)


def renewal_eligibility_with(
    award: Award, academic: Academic | None, *, today: date, declares_no_failing: bool | None
) -> EligibilityResult:
    """The renewal rules for an award on school and grades the caller already read."""
    return evaluate_renewal(
        award.program,
        academic,
        today=today,
        term=application_term(today),
        declares_no_failing=declares_no_failing,
    )


ONE_SCHOLARSHIP_TEXT = "Not holding another scholarship."


def _one_at_a_time(result: EligibilityResult, elsewhere: str) -> EligibilityResult:
    """`result` with an unmet "one scholarship at a time" check (spec §4.5): no Apply.
    `elsewhere` names the program of the award the student holds."""
    reason = ONE_SCHOLARSHIP.format(program=elsewhere)
    check = Check("one_scholarship", CheckState.UNMET, ONE_SCHOLARSHIP_TEXT, reason, "")
    return replace(result, eligible=False, checks=(*result.checks, check), tier_candidates=())


def match_page(user: User, *, today: date) -> MatchPage:
    """Everything the match page shows. Reads only: it never creates a profile."""
    term = application_term(today)
    profile = profile_for(user)
    if profile is None:
        return MatchPage(profile=None, academic=None, term=term, matches=[])
    academic = _academic(profile)
    held = Q(
        Exists(
            Award.objects.filter(
                profile=profile, program=OuterRef("pk"), status__in=Award.HELD_STATUSES
            )
        )
    )
    if term is not None:
        held |= Q(
            Exists(
                Application.objects.filter(
                    profile=profile,
                    program=OuterRef("pk"),
                    term=term,
                    status=Application.Status.APPROVED,
                )
            )
        )
    flags: dict[str, Q] = {"held": held}
    if term is not None:  # no term, nothing rejected this term
        flags["rejected"] = Q(
            Exists(
                Application.objects.filter(
                    profile=profile,
                    program=OuterRef("pk"),
                    term=term,
                    status=Application.Status.REJECTED,
                )
            )
        )
    # The program of an award held elsewhere, earliest first as held_award_elsewhere picks it:
    # a subquery, so the one-scholarship check costs no query of its own.
    annotations: dict[str, Q | Subquery] = {
        **flags,
        "elsewhere": Subquery(
            Award.objects.filter(profile=profile, status__in=Award.HELD_STATUSES)
            .exclude(program=OuterRef("pk"))
            .order_by("started_term__sort_key", "pk")
            .values("program__name")[:1]
        ),
    }
    programs = list(
        Program.objects.filter(is_active=True)
        .annotate(**annotations)
        .prefetch_related("allowed_schools")
        .order_by("name")
    )
    open_ids: dict[int, int] = {}
    behalf_ids: set[int] = set()
    if term is not None:
        for program_id, pk, on_behalf in Application.objects.filter(
            profile=profile, term=term, status__in=Application.OPEN_STATUSES
        ).values_list("program_id", "pk", "on_behalf"):
            open_ids[program_id] = pk
            if on_behalf:
                behalf_ids.add(program_id)
    tiers = tiers_in_force_for(programs, term) if term is not None else {}

    def result_for(program: Program) -> EligibilityResult:
        result = _evaluate(profile, program, academic, term, today, tiers.get(program.pk, []))
        held_elsewhere = getattr(program, "elsewhere", None)
        return result if not held_elsewhere else _one_at_a_time(result, held_elsewhere)

    matches = [
        ProgramMatch(
            program=program,
            result=result_for(program),
            open_application_id=open_ids.get(program.pk),
            open_on_behalf=program.pk in behalf_ids,
            held=bool(getattr(program, "held", False)),
            rejected=bool(getattr(program, "rejected", False)),
        )
        for program in programs
    ]
    return MatchPage(
        profile=profile,
        academic=academic,
        term=term,
        matches=matches,
    )
