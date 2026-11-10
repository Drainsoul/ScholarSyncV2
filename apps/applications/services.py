"""Student application writes. Rows are re-read under locks; audit data holds codes and ids only.

Lock order: the StudentProfile row, then the Application row. Opposite orders deadlock.
"""

from datetime import date
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application, Document, DocumentFile
from apps.applications.selectors import missing_documents, open_application, own_applications
from apps.core import audit
from apps.core.transitions import InvalidTransition, assert_transition
from apps.files.policy import MB, join_types
from apps.files.selectors import usable_file
from apps.matching.eligibility import Academic, EligibilityResult
from apps.matching.legacy_model import Hint, hint_for
from apps.matching.selectors import eligibility_for, eligibility_with
from apps.programs.models import BenefitTier, Program, RequiredDocument
from apps.programs.selectors import application_term
from apps.students.completion import completion
from apps.students.models import EducationRecord, StudentProfile
from apps.students.selectors import current_education
from apps.workspace.emails import enqueue

UPLOAD_AGAIN = "Upload the file again."
ALREADY_SUBMITTED = "This application has already been submitted."
SNAPSHOT_VERSION = 1


def _require_student(user: User) -> None:
    if not user.is_student:
        raise PermissionDenied("Only students can apply.")


def _locked_application(user: User, pk: int) -> Application:
    """The student's own application, locked. Http404 for anyone else's."""
    application = (
        own_applications(user)
        .select_for_update(of=("self",))
        .select_related("program", "term")
        .filter(pk=pk)
        .first()
    )
    if application is None:
        raise Http404("No such application.")
    return application


def _lock_profile_then_application(
    user: User, application: Application
) -> tuple[StudentProfile, Application]:
    profile_id = (
        own_applications(user)
        .filter(pk=application.pk)
        .values_list("profile_id", flat=True)
        .first()
    )
    if profile_id is None:
        raise Http404("No such application.")
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    locked = _locked_application(user, application.pk)
    if locked.profile_id != profile.pk:  # cannot change, but never trust an earlier read
        raise Http404("No such application.")
    return profile, locked


def _first_reason(result: EligibilityResult) -> str:
    return result.reasons[0]


@transaction.atomic
def start_application(
    *, user: User, program: Program, request: HttpRequest | None = None
) -> Application:
    _require_student(user)
    active = Program.objects.filter(pk=program.pk, is_active=True).first()
    if active is None:
        raise Http404("No such program.")
    profile = StudentProfile.objects.select_for_update().filter(user=user).first()
    if profile is None:
        raise ValidationError("Start your profile first.")
    today = timezone.localdate()
    term = application_term(today)
    if term is None:
        raise ValidationError(_first_reason(eligibility_for(profile, active, today=today)))
    existing = open_application(profile, active, term)
    if existing is not None:
        return existing
    result = eligibility_for(profile, active, today=today)
    if not result.eligible:
        raise ValidationError(_first_reason(result))
    try:
        with transaction.atomic():
            application = Application.objects.create(
                profile=profile,
                program=active,
                term=term,
                kind=Application.Kind.NEW,
                status=Application.Status.DRAFT,
                created_by=user,
            )
    except IntegrityError:
        # Another path committed an open application after we looked: the partial index caught it.
        existing = open_application(profile, active, term)
        if existing is None:
            raise
        return existing
    audit.record(
        actor=user,
        action="application.started",
        target=application,
        program=active,
        request=request,
        data={},
    )
    return application


def _applies(requirement: RequiredDocument, application: Application) -> bool:
    return requirement.program_id == application.program_id and requirement.applies_to in (
        application.kind,
        RequiredDocument.AppliesTo.BOTH,
    )


def _megabytes(size: int) -> str:
    return f"{size / MB:g}"


@transaction.atomic
def attach_document(
    *,
    user: User,
    application: Application,
    requirement: RequiredDocument,
    file_id: object,
    request: HttpRequest | None = None,
) -> Document:
    _require_student(user)
    locked = _locked_application(user, application.pk)
    if not locked.is_editable:
        raise ValidationError("You can't change documents after submitting.")
    fresh = RequiredDocument.objects.filter(pk=requirement.pk).first()
    if fresh is None or not _applies(fresh, locked):
        raise Http404("No such document.")
    file = usable_file(user, file_id, "document")
    if file is None or DocumentFile.objects.filter(file=file).exists():
        raise ValidationError(UPLOAD_AGAIN)
    if file.sniffed_type not in fresh.accepted_types:
        raise ValidationError(f"This document must be a {join_types(fresh.accepted_types)} file.")
    if file.size > fresh.max_bytes:
        raise ValidationError(f"This file is larger than {_megabytes(fresh.max_bytes)} MB.")
    document, _ = Document.objects.get_or_create(application=locked, requirement=fresh)
    if document.status == Document.Status.APPROVED:
        raise ValidationError("This document has been approved and can't be replaced.")
    if document.status == Document.Status.DECLINED:
        assert_transition(document, Document.Status.PENDING)
        document.status = Document.Status.PENDING
        document.decline_reason = ""
        document.save(update_fields=["status", "decline_reason", "updated_at"])
    last = document.files.aggregate(last=Max("version"))["last"] or 0
    document.files.filter(is_current=True).update(is_current=False, updated_at=timezone.now())
    version = last + 1
    DocumentFile.objects.create(document=document, file=file, version=version, is_current=True)
    audit.record(
        actor=user,
        action="document.uploaded",
        target=document,
        program=locked.program,
        request=request,
        data={"requirement": fresh.code, "version": version},
    )
    return document


def _hint_data(hint: Hint | str) -> dict[str, Any]:
    if isinstance(hint, str):
        return {"reason": hint}
    return {
        "label": hint.label,
        "program": hint.program_slug,
        "merit": hint.merit,
        "probability": hint.probability,
    }


def _snapshot(
    profile: StudentProfile, academic: Academic, result: EligibilityResult, today: date
) -> dict[str, Any]:
    return {
        "version": SNAPSHOT_VERSION,
        "evaluated_on": today.isoformat(),
        "eligible": result.eligible,
        "checks": [
            {"code": check.code, "state": check.state.value, "reason": check.reason}
            for check in result.checks
        ],
        "tier_candidates": [tier.code for tier in result.tier_candidates],
        "merit_likely": result.merit_likely,
        "hint": _hint_data(hint_for(profile, academic)),
    }


def _copy_academics(application: Application, record: EducationRecord) -> None:
    """Freeze the current school and grades. A listed school replaces the typed name and type."""
    school = record.school
    application.school = school
    application.school_name = "" if school is not None else record.school_name
    application.school_type = "" if school is not None else record.school_type
    application.gwa_scale = school.grading_scale if school is not None else record.gwa_scale
    application.course = record.course
    application.year_level = record.year_level
    application.gwa = record.gwa
    application.units = record.units


def _choose_tier(result: EligibilityResult, tier: BenefitTier | None) -> BenefitTier:
    candidates = list(result.tier_candidates)
    if not candidates:
        raise ValidationError("This program has no allowance tiers set up yet.")
    if tier is None:
        if len(candidates) == 1:
            return candidates[0]
        raise ValidationError("Choose an allowance tier.")
    for candidate in candidates:
        if candidate.pk == tier.pk:
            return candidate
    raise ValidationError("Choose one of this program's allowance tiers.")


def application_url(application: Application) -> str:
    return settings.SITE_URL + reverse("applications:detail", args=[application.pk])


@transaction.atomic
def submit_application(
    *,
    user: User,
    application: Application,
    tier: BenefitTier | None,
    request: HttpRequest | None = None,
) -> Application:
    _require_student(user)
    profile, locked = _lock_profile_then_application(user, application)
    try:
        assert_transition(locked, Application.Status.SUBMITTED)
    except InvalidTransition:
        if locked.status in (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW):
            raise ValidationError(ALREADY_SUBMITTED) from None
        raise
    from_draft = locked.status == Application.Status.DRAFT
    today = timezone.localdate()
    if from_draft:
        term = application_term(today)
        if term is None or locked.term_id != term.pk:
            raise ValidationError(
                f"This application was for {locked.term}, which has ended. "
                "Withdraw it and start a new one."
            )
    missing = missing_documents(locked)
    if missing:
        raise ValidationError(f"Upload {missing[0].label} before you submit.")
    update_fields = ["status", "submitted_at", "updated_at"]
    data: dict[str, object] = {}
    if from_draft:
        sections = completion(profile, family=[], education=[]).sections
        if not next(section for section in sections if section.key == "personal").done:
            raise ValidationError("Finish your personal details before you submit.")
        # Read the school and grades once: what is evaluated is exactly what is frozen.
        record = current_education(profile)
        academic = Academic.from_record(record) if record is not None else None
        result = eligibility_with(profile, locked.program, academic, today=today)
        if not result.eligible:
            raise ValidationError(_first_reason(result))
        chosen = _choose_tier(result, tier)
        assert record is not None and academic is not None  # eligibility needs a current school
        _copy_academics(locked, record)
        locked.requested_tier = chosen
        locked.match_snapshot = _snapshot(profile, academic, result, today)
        update_fields += [
            "school",
            "school_name",
            "school_type",
            "gwa_scale",
            "course",
            "year_level",
            "gwa",
            "units",
            "requested_tier",
            "match_snapshot",
        ]
        action, data = "application.submitted", {"tier": chosen.code}
    else:
        action = "application.resubmitted"
    locked.status = Application.Status.SUBMITTED
    locked.submitted_at = timezone.now()
    locked.save(update_fields=update_fields)
    audit.record(
        actor=user,
        action=action,
        target=locked,
        program=locked.program,
        request=request,
        data=data,
    )
    enqueue(
        to=user.email,
        kind="application_received",
        context={
            "full_name": profile.full_name,
            "program_name": locked.program.name,
            "application_url": application_url(locked),
        },
    )
    return locked


@transaction.atomic
def withdraw_application(
    *, user: User, application: Application, request: HttpRequest | None = None
) -> Application:
    _require_student(user)
    _, locked = _lock_profile_then_application(user, application)
    try:
        assert_transition(locked, Application.Status.WITHDRAWN)
    except InvalidTransition:
        if locked.status == Application.Status.UNDER_REVIEW:
            raise ValidationError(
                "This application is being reviewed and can't be withdrawn. "
                "Contact the scholarship office."
            ) from None
        raise
    locked.status = Application.Status.WITHDRAWN
    locked.save(update_fields=["status", "updated_at"])
    audit.record(
        actor=user,
        action="application.withdrawn",
        target=locked,
        program=locked.program,
        request=request,
    )
    return locked
