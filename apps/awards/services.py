"""Award writes. Audit data holds codes and ids only."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.core.transitions import assert_transition
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import current_term, tiers_in_force
from apps.students.models import StudentProfile

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


NEED_HOLD_REASON = "Say why you're putting this award on hold."
NEED_END_REASON = "Say why you're ending this award."
STATUS_REASON_TOO_LONG = "Keep the reason under 1,000 characters."
MAX_STATUS_REASON = 1000
FOREIGN_TIER = "Choose one of this program's allowance tiers."
STATUS_LABELS: dict[str, str] = {
    Award.Status.SUSPENDED: "Put on hold",
    Award.Status.ACTIVE: "Reinstate",
    Award.Status.INACTIVE: "End award",
    Award.Status.GRADUATED: "Mark graduated",
}
_NEED_REASON: dict[str, str] = {
    Award.Status.SUSPENDED: NEED_HOLD_REASON,
    Award.Status.INACTIVE: NEED_END_REASON,
}


def _lock_award(actor: User, program: Program, pk: int) -> tuple[StudentProfile, Award]:
    """The program's award `pk` and its profile, locked profile first. Http404 otherwise."""
    require_program_staff(actor, program)
    profile_id = (
        Award.objects.filter(program=program, pk=pk).values_list("profile_id", flat=True).first()
    )
    if profile_id is None:
        raise Http404("No such scholar.")
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    award = (
        Award.objects.select_for_update(of=("self",))
        .select_related("program", "tier")
        .filter(pk=pk, program=program)
        .first()
    )
    if award is None or award.profile_id != profile.pk:  # never trust the earlier read
        raise Http404("No such scholar.")
    return profile, award


@transaction.atomic
def update_award(
    *,
    actor: User,
    program: Program,
    award: Award,
    student_number: str,
    notes: str,
    tier: BenefitTier,
    request: HttpRequest | None = None,
) -> Award:
    """The student number, notes and tier. A new tier must be in force for the current term."""
    _, locked = _lock_award(actor, program, award.pk)
    if tier.pk != locked.tier_id:
        term = current_term()
        in_force = {row.pk for row in tiers_in_force(program, term)} if term is not None else set()
        if tier.pk not in in_force:
            raise ValidationError(FOREIGN_TIER)
    values = {"student_number": student_number.strip()[:50], "notes": notes.strip()}
    changed = [field for field, value in values.items() if getattr(locked, field) != value]
    for field in changed:
        setattr(locked, field, values[field])
    data: dict[str, object] = {}
    if tier.pk != locked.tier_id:
        locked.tier = tier
        changed.append("tier")
        data["tier"] = tier.code
    if not changed:
        return locked
    locked.save(update_fields=[*changed, "updated_at"])
    audit.record(
        actor=actor,
        action="award.updated",
        target=locked,
        program=program,
        request=request,
        data={"fields": changed, **data},
    )
    return locked


def _ending_term(award: Award) -> AcademicTerm:
    """The current term, or (with none set) the award's latest recorded term."""
    term = current_term()
    if term is not None:
        return term
    latest = award.terms.select_related("term").order_by("-term__sort_key").first()
    return latest.term if latest is not None else award.started_term


@transaction.atomic
def change_status(
    *,
    actor: User,
    program: Program,
    award: Award,
    to: str,
    reason: str,
    request: HttpRequest | None = None,
) -> Award:
    """Hold, reinstate, end or graduate. The reason is free text: it stays out of audit data."""
    _, locked = _lock_award(actor, program, award.pk)
    assert_transition(locked, to)
    reason = reason.strip()
    if to in _NEED_REASON and not reason:
        raise ValidationError(_NEED_REASON[to])
    if len(reason) > MAX_STATUS_REASON:
        raise ValidationError(STATUS_REASON_TOO_LONG)
    previous = locked.status
    locked.status = to
    if to == Award.Status.ACTIVE:
        locked.status_reason = ""
        locked.ended_term = None
    else:
        locked.status_reason = reason
        if to in (Award.Status.INACTIVE, Award.Status.GRADUATED):
            locked.ended_term = _ending_term(locked)
    try:
        with transaction.atomic():  # a savepoint, so the outer transaction survives the error
            locked.save(update_fields=["status", "status_reason", "ended_term", "updated_at"])
    except IntegrityError as exc:
        if not _violates(exc, ONE_ACTIVE_PER_PROGRAM):
            raise
        raise ValidationError(already_holds(program)) from None
    audit.record(
        actor=actor,
        action="award.status_changed",
        target=locked,
        program=program,
        request=request,
        data={"from": previous, "to": to},
    )
    return locked
