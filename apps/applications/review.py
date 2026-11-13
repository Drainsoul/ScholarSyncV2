"""Staff review writes. Rows are re-read under locks; audit data holds codes and ids only.

Lock order: the StudentProfile row, then the Application row, then any Document row. The student
services lock in the same order; opposite orders deadlock.

Every lookup goes through `applications_for_program(program)`: another program's id is a 404, and
nothing changes or is audited.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application, Document
from apps.applications.review_selectors import applications_for_program
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.core.transitions import assert_transition
from apps.programs.models import Program
from apps.students.models import StudentProfile

ALREADY_STARTED = "Someone has already started reviewing this application."
START_FIRST = "Start the review before you check documents."
NO_CURRENT_FILE = "This document has no file to check."
NEED_DECLINE_REASON = "Say why you're declining this document."
DECLINE_REASON_TOO_LONG = "Keep the reason under 500 characters."
MAX_DECLINE_REASON = 500


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
