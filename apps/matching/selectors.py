from dataclasses import dataclass
from datetime import date

from django.db.models import Exists, OuterRef, Q

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award
from apps.matching.eligibility import Academic, EligibilityResult, evaluate
from apps.matching.legacy_model import Hint, hint_for
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import application_term, tiers_in_force
from apps.students.models import StudentProfile
from apps.students.selectors import current_education, profile_for


@dataclass(frozen=True)
class ProgramMatch:
    program: Program
    result: EligibilityResult
    open_application_id: int | None  # the student's open application for this program and term
    held: bool = False  # an approved application this term, or an active award


@dataclass(frozen=True)
class MatchPage:
    profile: StudentProfile | None
    academic: Academic | None
    term: AcademicTerm | None
    matches: list[ProgramMatch]  # active programs, by name
    hint: Hint | str | None  # None only when there is no profile


def _academic(profile: StudentProfile) -> Academic | None:
    record = current_education(profile)
    return Academic.from_record(record) if record is not None else None


def _evaluate(
    profile: StudentProfile,
    program: Program,
    academic: Academic | None,
    term: AcademicTerm | None,
    today: date,
) -> EligibilityResult:
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


def match_page(user: User, *, today: date) -> MatchPage:
    """Everything the match page shows. Reads only: it never creates a profile."""
    term = application_term(today)
    profile = profile_for(user)
    if profile is None:
        return MatchPage(profile=None, academic=None, term=term, matches=[], hint=None)
    academic = _academic(profile)
    held = Q(
        Exists(
            Award.objects.filter(
                profile=profile, program=OuterRef("pk"), status=Award.Status.ACTIVE
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
    programs = list(
        Program.objects.filter(is_active=True)
        .annotate(held=held)
        .prefetch_related("allowed_schools")
        .order_by("name")
    )
    open_ids: dict[int, int] = {}
    if term is not None:
        open_ids = dict(
            Application.objects.filter(
                profile=profile, term=term, status__in=Application.OPEN_STATUSES
            ).values_list("program_id", "pk")
        )
    matches = [
        ProgramMatch(
            program=program,
            result=_evaluate(profile, program, academic, term, today),
            open_application_id=open_ids.get(program.pk),
            held=bool(getattr(program, "held", False)),
        )
        for program in programs
    ]
    return MatchPage(
        profile=profile,
        academic=academic,
        term=term,
        matches=matches,
        hint=hint_for(profile, academic),
    )
