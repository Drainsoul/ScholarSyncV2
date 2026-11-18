"""Report writes: send, send again, accept or return (spec §4.8, M11c).

Audit data and notifications never hold the title, description or note (free text)."""

from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import record
from apps.core.permissions import require_office, require_program_staff
from apps.core.text import normalize_newlines
from apps.files.models import StoredFile
from apps.programs.models import Program
from apps.workspace.services import notify

from .models import Report, ReportFile

PERIOD_ORDER = "The period must end on or after its start."
NEED_PDF = "Upload the report as a PDF."
FILE_USED = "Upload the file again."
NOT_RETURNED = "This report is no longer returned."
NEED_NOTE = "Say what the program should change."


def period_label(start: date, end: date) -> str:
    """ "1 August 2026 to 31 October 2026"."""
    return f"{start.day} {start:%B %Y} to {end.day} {end:%B %Y}"


def office_url(report: Report) -> str:
    return f"/office/reports/{report.pk}/"


def staff_url(report: Report) -> str:
    return f"/staff/{report.program.slug}/reports/{report.pk}/"


def _check_period(start: date, end: date) -> None:
    if end < start:
        raise ValidationError(PERIOD_ORDER)


def _attach(report: Report, file: StoredFile) -> None:
    if file.purpose != StoredFile.Purpose.REPORT or file.status != StoredFile.Status.READY:
        raise ValidationError(NEED_PDF)
    if _already_attached(file):
        raise ValidationError(FILE_USED)
    try:
        with transaction.atomic():
            ReportFile.objects.create(report=report, file=file)
    except IntegrityError:
        # A second post raced past the check (a double click): the file is taken.
        raise ValidationError(FILE_USED) from None


def _already_attached(file: StoredFile) -> bool:
    return ReportFile.objects.filter(file=file).exists()


def _tell_office(report: Report, title: str) -> None:
    body = f"{period_label(report.period_start, report.period_end)}."
    for office in User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).order_by("pk"):
        notify(user=office, kind="report_submitted", title=title, body=body, url=office_url(report))


OFFICE_CANT_SEND = "Reports come from programs. The office reviews them."


def _require_sender(actor: User, program: Program) -> None:
    """Program staff and heads send reports; the office reviews them (M14)."""
    if actor.is_super_admin:
        raise PermissionDenied(OFFICE_CANT_SEND)
    require_program_staff(actor, program)


@transaction.atomic
def submit_report(
    *,
    actor: User,
    program: Program,
    title: str,
    period_start: date,
    period_end: date,
    description: str,
    file: StoredFile,
    request: HttpRequest | None = None,
) -> Report:
    _require_sender(actor, program)
    _check_period(period_start, period_end)
    report = Report.objects.create(
        program=program,
        title=title.strip(),
        period_start=period_start,
        period_end=period_end,
        description=normalize_newlines(description).strip(),
        submitted_by=actor,
        submitted_at=timezone.now(),
    )
    _attach(report, file)
    record(
        actor=actor,
        action="report.submitted",
        target=report,
        program=program,
        data={"report": report.pk},
        request=request,
    )
    _tell_office(report, f"{program.name} sent a report for review")
    return report


@transaction.atomic
def resubmit_report(
    *,
    actor: User,
    report: Report,
    title: str,
    period_start: date,
    period_end: date,
    description: str,
    file: StoredFile | None,
    request: HttpRequest | None = None,
) -> Report:
    _require_sender(actor, report.program)
    locked = Report.objects.select_for_update().select_related("program").get(pk=report.pk)
    if locked.status != Report.Status.RETURNED:
        raise ValidationError(NOT_RETURNED)
    _check_period(period_start, period_end)
    locked.title = title.strip()
    locked.period_start = period_start
    locked.period_end = period_end
    locked.description = normalize_newlines(description).strip()
    locked.status = Report.Status.SUBMITTED
    locked.submitted_by = actor
    locked.submitted_at = timezone.now()
    locked.save()
    if file is not None:
        _attach(locked, file)
    record(
        actor=actor,
        action="report.resubmitted",
        target=locked,
        program=locked.program,
        data={"report": locked.pk},
        request=request,
    )
    _tell_office(locked, f"{locked.program.name} sent a returned report back")
    return locked


@transaction.atomic
def decide_report(
    *,
    actor: User,
    report: Report,
    accept: bool,
    note: str,
    request: HttpRequest | None = None,
) -> Report:
    require_office(actor)
    locked = (
        Report.objects.select_for_update()
        .select_related("program", "submitted_by")
        .get(pk=report.pk)
    )
    if locked.status != Report.Status.SUBMITTED:
        raise ValidationError(f"This report was already {locked.status}.")
    note = normalize_newlines(note).strip()
    if not accept and not note:
        raise ValidationError(NEED_NOTE)
    locked.status = Report.Status.ACCEPTED if accept else Report.Status.RETURNED
    locked.reviewed_by = actor
    locked.reviewed_at = timezone.now()
    locked.review_note = note
    locked.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    record(
        actor=actor,
        action="report.accepted" if accept else "report.returned",
        target=locked,
        program=locked.program,
        data={"report": locked.pk},
        request=request,
    )
    program = locked.program.name
    if accept:
        kind, title, body = "report_accepted", f"The office accepted your {program} report", ""
    else:
        kind = "report_returned"
        title = f"The office returned your {program} report"
        body = "Open it to see what to change."
    notify(
        user=locked.submitted_by,
        kind=kind,
        title=title,
        body=body,
        url=staff_url(locked),
    )
    return locked
