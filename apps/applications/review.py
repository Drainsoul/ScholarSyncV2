"""Staff review writes. Rows are re-read under locks; audit data holds codes and ids only.

Lock order: the StudentProfile row, then the Application row, then any Document row. The student
services lock in the same order; opposite orders deadlock.

Every lookup goes through `applications_for_program(program)`: another program's id is a 404, and
nothing changes or is audited.
"""

from dataclasses import dataclass
from typing import Literal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application, Document
from apps.applications.review_selectors import applications_for_program
from apps.applications.selectors import undecided_rows
from apps.applications.services import application_url
from apps.awards.models import Award
from apps.awards.selectors import holds_active_award
from apps.awards.services import already_holds, award_from_application
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.core.transitions import assert_transition
from apps.programs.models import BenefitTier, Program
from apps.programs.selectors import tiers_in_force
from apps.students.models import StudentProfile
from apps.workspace.emails import enqueue

ALREADY_STARTED = "Someone has already started reviewing this application."
START_FIRST = "Start the review before you check documents."
NO_CURRENT_FILE = "This document has no file to check."
NEED_DECLINE_REASON = "Say why you're declining this document."
DECLINE_REASON_TOO_LONG = "Keep the reason under 500 characters."
MAX_DECLINE_REASON = 500
NEED_RETURN_REASON = "Say what the student needs to fix."
NEED_REJECT_REASON = "Say why the application is not approved."
DECISION_REASON_TOO_LONG = "Keep the reason under 1,000 characters."
MAX_DECISION_REASON = 1000
NOT_DECIDED = "Approve or decline every document first: {label}."
NEVER_UPLOADED = "{label} was never uploaded. Return the application so the student can add it."
TIER_GONE = "The requested tier is no longer offered. Choose another tier."
FOREIGN_TIER = "Choose one of this program's allowance tiers."
MAX_BULK = 100
BULK_TOO_MANY = "Choose at most 100 applications at a time."
BULK_NOT_FOUND = "Not found."
# The application_decided email template branches on these exact values.
OUTCOME_APPROVED = "approved"
OUTCOME_NOT_APPROVED = "not approved"


def _lock_for_staff(actor: User, program: Program, pk: int) -> tuple[StudentProfile, Application]:
    """The program's application `pk` and its profile, locked profile first. Http404 otherwise."""
    require_program_staff(actor, program)
    profile_id = (
        applications_for_program(program).filter(pk=pk).values_list("profile_id", flat=True).first()
    )
    if profile_id is None:
        raise Http404("No such application.")
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    locked = (
        Application.objects.select_for_update(of=("self",))
        .select_related("program", "term", "requested_tier")
        .filter(pk=pk, pk__in=applications_for_program(program).values("pk"))
        .first()
    )
    if locked is None or locked.profile_id != profile.pk:  # never trust the earlier read
        raise Http404("No such application.")
    return profile, locked


@transaction.atomic
def start_review(
    *,
    actor: User,
    program: Program,
    application: Application,
    request: HttpRequest | None = None,
) -> Application:
    _, locked = _lock_for_staff(actor, program, application.pk)
    if locked.status == Application.Status.UNDER_REVIEW:
        raise ValidationError(ALREADY_STARTED)
    assert_transition(locked, Application.Status.UNDER_REVIEW)
    locked.status = Application.Status.UNDER_REVIEW
    locked.save(update_fields=["status", "updated_at"])
    audit.record(
        actor=actor,
        action="application.review_started",
        target=locked,
        program=locked.program,
        request=request,
    )
    return locked


def _lock_document(
    actor: User, program: Program, application: Application, document_id: int
) -> Document:
    """The document of the locked, under-review application, itself locked and holding a file."""
    _, locked = _lock_for_staff(actor, program, application.pk)
    document = (
        Document.objects.select_for_update().filter(pk=document_id, application=locked).first()
    )
    if document is None:
        raise Http404("No such document.")
    if locked.status != Application.Status.UNDER_REVIEW:
        raise ValidationError(START_FIRST)
    if not document.files.filter(is_current=True).exists():
        raise ValidationError(NO_CURRENT_FILE)
    return document


def _decide(
    *,
    actor: User,
    program: Program,
    document: Document,
    status: Document.Status,
    action: str,
    reason: str = "",
    request: HttpRequest | None,
) -> Document:
    document.status = status
    document.decline_reason = reason
    document.reviewed_by = actor
    document.reviewed_at = timezone.now()
    document.save(
        update_fields=["status", "decline_reason", "reviewed_by", "reviewed_at", "updated_at"]
    )
    audit.record(
        actor=actor,
        action=action,
        target=document,
        program=program,
        request=request,
        data={"requirement": document.requirement.code},
    )
    return document


@transaction.atomic
def approve_document(
    *,
    actor: User,
    program: Program,
    application: Application,
    document_id: int,
    request: HttpRequest | None = None,
) -> Document:
    document = _lock_document(actor, program, application, document_id)
    assert_transition(document, Document.Status.APPROVED)
    return _decide(
        actor=actor,
        program=program,
        document=document,
        status=Document.Status.APPROVED,
        action="document.approved",
        request=request,
    )


@transaction.atomic
def decline_document(
    *,
    actor: User,
    program: Program,
    application: Application,
    document_id: int,
    reason: str,
    request: HttpRequest | None = None,
) -> Document:
    document = _lock_document(actor, program, application, document_id)
    assert_transition(document, Document.Status.DECLINED)
    reason = reason.strip()
    if not reason:
        raise ValidationError(NEED_DECLINE_REASON)
    if len(reason) > MAX_DECLINE_REASON:
        raise ValidationError(DECLINE_REASON_TOO_LONG)
    return _decide(
        actor=actor,
        program=program,
        document=document,
        status=Document.Status.DECLINED,
        action="document.declined",
        reason=reason,
        request=request,
    )


def _email(
    profile: StudentProfile, application: Application, *, kind: str, outcome: str | None
) -> None:
    """The student's email. Reasons and notes are free text: they stay out of it."""
    if profile.user is None:
        return
    context = {
        "full_name": profile.full_name,
        "program_name": application.program.name,
        "application_url": application_url(application),
    }
    if outcome is not None:
        context["outcome"] = outcome
    enqueue(to=profile.user.email, kind=kind, context=context)


def _finish(
    *,
    actor: User,
    program: Program,
    application: Application,
    reason: str,
    need_reason: str,
    status: Application.Status,
    action: str,
    kind: str,
    outcome: str | None,
    request: HttpRequest | None,
) -> Application:
    """Return or reject: under the locks, check the state and the reason, save, audit, email."""
    profile, locked = _lock_for_staff(actor, program, application.pk)
    assert_transition(locked, status)
    reason = reason.strip()
    if not reason:
        raise ValidationError(need_reason)
    if len(reason) > MAX_DECISION_REASON:
        raise ValidationError(DECISION_REASON_TOO_LONG)
    update_fields = ["status", "decision_reason", "updated_at"]
    if status == Application.Status.REJECTED:  # a return is not a decision
        locked.decided_at = timezone.now()
        locked.decided_by = actor
        update_fields += ["decided_at", "decided_by"]
    locked.status = status
    locked.decision_reason = reason
    locked.save(update_fields=update_fields)
    audit.record(
        actor=actor,
        action=action,
        target=locked,
        program=locked.program,
        request=request,
    )
    _email(profile, locked, kind=kind, outcome=outcome)
    return locked


@transaction.atomic
def return_application(
    *,
    actor: User,
    program: Program,
    application: Application,
    reason: str,
    request: HttpRequest | None = None,
) -> Application:
    return _finish(
        actor=actor,
        program=program,
        application=application,
        reason=reason,
        need_reason=NEED_RETURN_REASON,
        status=Application.Status.RETURNED,
        action="application.returned",
        kind="application_returned",
        outcome=None,
        request=request,
    )


@transaction.atomic
def reject_application(
    *,
    actor: User,
    program: Program,
    application: Application,
    reason: str,
    request: HttpRequest | None = None,
) -> Application:
    return _finish(
        actor=actor,
        program=program,
        application=application,
        reason=reason,
        need_reason=NEED_REJECT_REASON,
        status=Application.Status.REJECTED,
        action="application.rejected",
        kind="application_decided",
        outcome=OUTCOME_NOT_APPROVED,
        request=request,
    )


def _approval_tier(locked: Application, tier: BenefitTier | None) -> BenefitTier:
    """The chosen tier, or the requested one, if in force for the application's term."""
    in_force = {row.pk: row for row in tiers_in_force(locked.program, locked.term)}
    if tier is not None:
        if tier.pk not in in_force:
            raise ValidationError(FOREIGN_TIER)
        return in_force[tier.pk]
    if locked.requested_tier_id is None or locked.requested_tier_id not in in_force:
        raise ValidationError(TIER_GONE)
    return in_force[locked.requested_tier_id]


@transaction.atomic
def approve_application(
    *,
    actor: User,
    program: Program,
    application: Application,
    tier: BenefitTier | None,
    note: str = "",
    request: HttpRequest | None = None,
) -> Award:
    """Approve under the locks, creating the award and its first scholar term."""
    profile, locked = _lock_for_staff(actor, program, application.pk)
    assert_transition(locked, Application.Status.APPROVED)
    undecided = undecided_rows(locked)
    # Deciding the others can't help while a required document is missing: name that one first.
    never_uploaded = [row for row in undecided if row.document is None]
    if never_uploaded:
        raise ValidationError(NEVER_UPLOADED.format(label=never_uploaded[0].requirement.label))
    if undecided:
        raise ValidationError(NOT_DECIDED.format(label=undecided[0].requirement.label))
    chosen = _approval_tier(locked, tier)
    if holds_active_award(profile, locked.program):
        raise ValidationError(already_holds(locked.program))
    note = note.strip()
    if len(note) > MAX_DECISION_REASON:
        raise ValidationError(DECISION_REASON_TOO_LONG)
    locked.status = Application.Status.APPROVED
    locked.decided_at = timezone.now()
    locked.decided_by = actor
    locked.decision_reason = note
    locked.save(
        update_fields=["status", "decided_at", "decided_by", "decision_reason", "updated_at"]
    )
    award = award_from_application(actor=actor, application=locked, tier=chosen, request=request)
    audit.record(
        actor=actor,
        action="application.approved",
        target=locked,
        program=locked.program,
        request=request,
        data={"tier": chosen.code, "award": award.pk},
    )
    _email(profile, locked, kind="application_decided", outcome=OUTCOME_APPROVED)
    return award


@dataclass(frozen=True)
class BulkResult:
    done: int
    skipped: list[tuple[str, str]]  # (applicant name, sentence)


def bulk_action(
    *,
    actor: User,
    program: Program,
    action: Literal["start_review", "approve"],
    ids: list[int],
    request: HttpRequest | None = None,
) -> BulkResult:
    """Run one single-row service per application, each in its own transaction.

    Not atomic as a whole: a refused row is skipped and the rest go on. Rows run in (profile, pk)
    order so two staff members bulk-acting on overlapping sets lock profiles in the same order.
    """
    require_program_staff(actor, program)  # a PermissionDenied is not a per-row skip
    wanted = list(dict.fromkeys(ids))
    if len(wanted) > MAX_BULK:
        raise ValidationError(BULK_TOO_MANY)
    found = {
        row.pk: row
        for row in applications_for_program(program).filter(pk__in=wanted).select_related("profile")
    }
    skipped: list[tuple[str, str]] = []
    done = 0
    for row in sorted(found.values(), key=lambda row: (row.profile_id, row.pk)):
        try:
            with transaction.atomic():
                if action == "start_review":
                    start_review(actor=actor, program=program, application=row, request=request)
                else:
                    approve_application(
                        actor=actor, program=program, application=row, tier=None, request=request
                    )
        except (ValidationError, Http404) as error:  # InvalidTransition is a ValidationError
            reason = " ".join(error.messages) if isinstance(error, ValidationError) else str(error)
            skipped.append((row.profile.full_name, reason))
        else:
            done += 1
    skipped.extend(("", BULK_NOT_FOUND) for pk in wanted if pk not in found)
    return BulkResult(done=done, skipped=skipped)
