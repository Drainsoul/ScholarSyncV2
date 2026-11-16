"""Award writes. Audit data holds codes and ids only."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.core import audit
from apps.programs.models import BenefitTier, Program

ONE_ACTIVE_PER_PROGRAM = "awards_one_active_per_program"


def already_holds(program: Program) -> str:
    return f"This student already holds an active {program.name} award."


def _violates(exc: IntegrityError, constraint: str) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


@transaction.atomic
def award_from_application(
    *,
    actor: User,
    application: Application,
    tier: BenefitTier,
    request: HttpRequest | None = None,
) -> Award:
    """The active award and its first scholar term for an application being approved.

    The caller holds the profile and application locks and has checked the tier; the unique
    index still guards against an active award written by any other path."""
    try:
        with transaction.atomic():  # a savepoint, so the outer transaction survives the error
            award = Award.objects.create(
                profile=application.profile,
                program=application.program,
                tier=tier,
                status=Award.Status.ACTIVE,
                source=Award.Source.APPLIED,
                source_application=application,
                started_term=application.term,
            )
    except IntegrityError as exc:
        if not _violates(exc, ONE_ACTIVE_PER_PROGRAM):
            raise
        raise ValidationError(already_holds(application.program)) from None
    ScholarTerm.objects.create(
        award=award,
        term=application.term,
        year_level=application.year_level,
        course=application.course,
        school=application.school,
        school_name=application.school_name,
        school_type=application.school_type,
        gwa=application.gwa,
        gwa_scale=application.gwa_scale,
        units=application.units,
        tier=tier,
        merit=application.match_snapshot.get("merit_likely") is True,
        compliance=ScholarTerm.Compliance.COMPLETE,  # approval needs every document approved
    )
    audit.record(
        actor=actor,
        action="award.created",
        target=award,
        program=application.program,
        request=request,
        data={
            "source": Award.Source.APPLIED.value,
            "application": application.pk,
            "tier": tier.code,
        },
    )
    return award
