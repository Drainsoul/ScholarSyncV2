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


AWARD_ON_HOLD = "This award is on hold. Reinstate it before approving the renewal."
AWARD_ENDED = "This award has ended, so the renewal can't be approved."
TERM_EXISTS = "This scholar already has a record for {term}."


@transaction.atomic
def term_from_renewal(
    *,
    actor: User,
    application: Application,
    tier: BenefitTier,
    request: HttpRequest | None = None,
) -> ScholarTerm:
    """The next scholar term of a renewal being approved; the award moves to `tier`.

    The caller holds the profile and application locks (lock order: profile, application, award).
    """
    assert application.award_id is not None  # applications_renewal_has_award
    award = Award.objects.select_for_update(of=("self",)).get(
        pk=application.award_id, profile_id=application.profile_id
    )
    if award.status == Award.Status.SUSPENDED:
        raise ValidationError(AWARD_ON_HOLD)
    if award.status != Award.Status.ACTIVE:
        raise ValidationError(AWARD_ENDED)
    if ScholarTerm.objects.filter(award=award, term=application.term).exists():
        raise ValidationError(TERM_EXISTS.format(term=application.term))
    record = ScholarTerm.objects.create(
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
    if award.tier_id != tier.pk:
        award.tier = tier
        award.save(update_fields=["tier", "updated_at"])
    audit.record(
        actor=actor,
        action="scholar_term.created",
        target=record,
        program=application.program,
        request=request,
        data={
            "award": award.pk,
            "term": application.term_id,
            "source": "renewal",
            "tier": tier.code,
        },
    )
    return record
