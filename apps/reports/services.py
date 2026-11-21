"""Report writes: send, send again, the head's review, accept or return (spec §4.8, M11c, rev 33).

A staff member's report goes to the program's head first; the head approves or returns it and
sends an approved one to the office. A head's own report goes to the office at once.

Audit data and notifications never hold the title, description or note (free text)."""

from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import record
from apps.core.permissions import require_office, require_program_head, require_program_staff
from apps.core.text import normalize_newlines
from apps.files.models import StoredFile
from apps.programs.models import Program, ProgramMembership
from apps.programs.selectors import membership_for
from apps.workspace.services import notify

from .models import Report, ReportFile

PERIOD_ORDER = "The period must end on or after its start."
NEED_PDF = "Upload the report as a PDF."
FILE_USED = "Upload the file again."
NOT_RETURNED = "This report is no longer returned."
NEED_NOTE = "Say what the program should change."
NO_HEAD = "This program has no head yet. Ask the scholarship office to add one."


def already(report: Report) -> str:
    """The refusal of a stale transition: "This report was already accepted."."""
    if report.status == Report.Status.APPROVED:
        return "This report was already approved."
    return f"This report was already {Report.Status(report.status).label.lower()}."


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


def program_heads(program: Program) -> list[User]:
    """The program's active heads, oldest account first."""
    return list(
        User.objects.filter(
            is_active=True,
            role=User.Role.STAFF,
            memberships__program=program,
            memberships__level=ProgramMembership.Level.HEAD,
        ).order_by("pk")
    )


def _tell_heads(report: Report) -> None:
    title = f"A {report.program.name} report is waiting for your review"
    body = f"{period_label(report.period_start, report.period_end)}."
    for head in program_heads(report.program):
        notify(user=head, kind="report_for_head", title=title, body=body, url=staff_url(report))


def is_program_head(actor: User, program: Program) -> bool:
    """A head of the program (never the office: it reviews reports, it doesn't send them)."""
    if actor.is_super_admin:
        return False
    membership = membership_for(actor, program)
    return membership is not None and membership.level == ProgramMembership.Level.HEAD


OFFICE_CANT_SEND = "Reports come from programs. The office reviews them."


def _require_sender(actor: User, program: Program) -> None:
    """Program staff and heads send reports; the office reviews them (M14)."""
    if actor.is_super_admin:
        raise PermissionDenied(OFFICE_CANT_SEND)
    require_program_staff(actor, program)


def _require_head(actor: User, program: Program) -> None:
    """A head of the program reviews and sends staff reports; never the office (rev 23)."""
    if actor.is_super_admin:
        raise PermissionDenied(OFFICE_CANT_SEND)
    require_program_head(actor, program)


def _send_to_office(report: Report, actor: User) -> str:
    """Mark the report sent by `actor` now. Returns the office's notification title, which says
    whether the office has seen this report before."""
    seen = report.sent_at is not None
    report.status = Report.Status.SUBMITTED
    report.sent_by = actor
    report.sent_at = timezone.now()
    name = report.program.name
    return f"{name} sent a returned report back" if seen else f"{name} sent a report for review"


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
    head = is_program_head(actor, program)
    now = timezone.now()
    report = Report.objects.create(
        program=program,
        title=title.strip(),
        period_start=period_start,
        period_end=period_end,
        description=normalize_newlines(description).strip(),
        status=Report.Status.SUBMITTED if head else Report.Status.WITH_HEAD,
        submitted_by=actor,
        submitted_at=now,
        sent_by=actor if head else None,
        sent_at=now if head else None,
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
    if head:
        _tell_office(report, f"{program.name} sent a report for review")
    else:
        _tell_heads(report)
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
    locked.submitted_by = actor
    locked.submitted_at = timezone.now()
    head = is_program_head(actor, locked.program)
    office_title = ""
    if head:
        office_title = _send_to_office(locked, actor)
    else:
        locked.status = Report.Status.WITH_HEAD
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
    if head:
        _tell_office(locked, office_title)
    else:
        _tell_heads(locked)
    return locked


def _lock(report: Report) -> Report:
    return (
        Report.objects.select_for_update()
        .select_related("program", "submitted_by")  # sent_by is nullable: no outer join
        .get(pk=report.pk)
    )


HEAD_REVIEW_FIELDS = [
    "status",
    "head_reviewed_by",
    "head_reviewed_at",
    "reviewed_by",
    "reviewed_at",
    "review_note",
]


def _head_review(report: Report, actor: User, status: str, note: str) -> None:
    """Record the head's review. A return, or an approval with a note, becomes the latest note;
    an approval without one keeps the office's earlier note in view ("Returned earlier")."""
    now = timezone.now()
    report.status = status
    report.head_reviewed_by = actor
    report.head_reviewed_at = now
    if note or status == Report.Status.RETURNED:
        report.reviewed_by = actor
        report.reviewed_at = now
        report.review_note = note
    report.save(update_fields=HEAD_REVIEW_FIELDS)


@transaction.atomic
def head_approve_report(
    *, actor: User, report: Report, note: str, request: HttpRequest | None = None
) -> Report:
    """A head of the program approves a staff member's report; sending it is a second step."""
    _require_head(actor, report.program)
    locked = _lock(report)
    if locked.status != Report.Status.WITH_HEAD:
        raise ValidationError(already(locked))
    _head_review(locked, actor, Report.Status.APPROVED, normalize_newlines(note).strip())
    record(
        actor=actor,
        action="report.head_approved",
        target=locked,
        program=locked.program,
        data={"report": locked.pk},
        request=request,
    )
    notify(
        user=locked.submitted_by,
        kind="report_head_approved",
        title=f"The head approved your {locked.program.name} report",
        body="",
        url=staff_url(locked),
    )
    return locked


@transaction.atomic
def head_return_report(
    *, actor: User, report: Report, note: str, request: HttpRequest | None = None
) -> Report:
    """A head of the program returns a staff member's report with a note."""
    _require_head(actor, report.program)
    locked = _lock(report)
    if locked.status != Report.Status.WITH_HEAD:
        raise ValidationError(already(locked))
    note = normalize_newlines(note).strip()
    if not note:
        raise ValidationError(NEED_NOTE)
    _head_review(locked, actor, Report.Status.RETURNED, note)
    record(
        actor=actor,
        action="report.head_returned",
        target=locked,
        program=locked.program,
        data={"report": locked.pk},
        request=request,
    )
    notify(
        user=locked.submitted_by,
        kind="report_head_returned",
        title=f"The head returned your {locked.program.name} report",
        body="Open it to see what to change.",
        url=staff_url(locked),
    )
    return locked


@transaction.atomic
def send_report_to_office(
    *, actor: User, report: Report, request: HttpRequest | None = None
) -> Report:
    """A head sends an approved report to the scholarship office."""
    _require_head(actor, report.program)
    locked = _lock(report)
    if locked.status != Report.Status.APPROVED:
        raise ValidationError(already(locked))
    office_title = _send_to_office(locked, actor)
    locked.save(update_fields=["status", "sent_by", "sent_at"])
    record(
        actor=actor,
        action="report.sent",
        target=locked,
        program=locked.program,
        data={"report": locked.pk},
        request=request,
    )
    _tell_office(locked, office_title)
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
    locked = _lock(report)
    if locked.status != Report.Status.SUBMITTED:
        raise ValidationError(already(locked))
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
    recipients = [locked.submitted_by]
    if locked.sent_by is not None and locked.sent_by_id != locked.submitted_by_id:
        recipients.append(locked.sent_by)  # the head who sent a staff member's report
    for recipient in recipients:
        notify(user=recipient, kind=kind, title=title, body=body, url=staff_url(locked))
    return locked
