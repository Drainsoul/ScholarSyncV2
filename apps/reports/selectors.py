"""Report reads (spec §4.8, M11c)."""

from datetime import datetime

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Min, Q, QuerySet
from django.http import Http404

from apps.accounts.models import User
from apps.core.permissions import require_program_staff
from apps.files.models import StoredFile
from apps.programs.models import Program

from .models import Report, ReportFile

REPORT_TABS_STAFF = {
    "all": "All",
    "with_head": "With the head",
    "approved": "Approved",
    "submitted": "With the office",
    "returned": "Returned",
    "accepted": "Accepted",
}
REPORT_TABS_OFFICE = {
    "submitted": "To review",
    "returned": "Returned",
    "accepted": "Accepted",
    "all": "All",
}


def staff_can_download_report(user: User, file: StoredFile) -> bool:
    """True when the file is a version of a report and the user is staff of its program (or the
    office), whoever uploaded it. Two queries at most."""
    row = ReportFile.objects.filter(file=file).select_related("report__program").first()
    if row is None:
        return False
    if user.is_super_admin and row.report.sent_at is None:
        return False  # the office sees only reports that were sent to it (rev 33)
    try:
        require_program_staff(user, row.report.program)
    except PermissionDenied:
        return False
    return True


def program_reports(program: Program, tab: str, *, office: bool = False) -> QuerySet[Report]:
    """The program's reports for a staff tab, newest first; an unknown tab is All. The office
    (on the program's pages) sees only the reports sent to it."""
    rows = (_sent() if office else Report.objects.all()).filter(program=program)
    rows = rows.select_related("program")
    if tab in Report.Status.values:
        rows = rows.filter(status=tab)
    return rows.order_by("-submitted_at", "-pk")


def _sent() -> QuerySet[Report]:
    """Reports the office sees: those sent to it at least once (rev 33)."""
    return Report.objects.filter(sent_at__isnull=False)


def office_reports(tab: str, program_id: int | None) -> QuerySet[Report]:
    """Every program's sent reports for an office tab: To review oldest sent first, the rest
    newest first."""
    rows = _sent().select_related("program")
    if program_id is not None:
        rows = rows.filter(program_id=program_id)
    if tab in Report.Status.values:
        rows = rows.filter(status=tab)
    if tab == Report.Status.SUBMITTED:
        return rows.order_by("sent_at", "pk")
    return rows.order_by("-sent_at", "-pk")


def staff_report(program: Program, pk: int, *, office: bool = False) -> Report:
    """One of the program's reports; another program's id is a 404, and so is, for the office,
    a report never sent to it."""
    report = (
        (_sent() if office else Report.objects.all())
        .filter(program=program, pk=pk)
        .select_related("program", "submitted_by", "reviewed_by", "sent_by")
        .first()
    )
    if report is None:
        raise Http404("No such report.")
    return report


def office_report(pk: int) -> Report:
    """A sent report; one the office has never been sent is a 404."""
    report = (
        _sent()
        .filter(pk=pk)
        .select_related("program", "submitted_by", "reviewed_by", "sent_by")
        .first()
    )
    if report is None:
        raise Http404("No such report.")
    return report


def report_files(report: Report) -> QuerySet[ReportFile]:
    return report.files.select_related("file").order_by("-created_at", "-pk")


def report_file(report: Report, pk: int) -> ReportFile:
    """One file of the report (any version), or 404."""
    found = report.files.select_related("file").filter(pk=pk).first()
    if found is None:
        raise Http404("No such file.")
    return found


def submitted_count() -> int:
    return Report.objects.filter(status=Report.Status.SUBMITTED).count()


def staff_nav_count(program: Program, *, head: bool = False, office: bool = False) -> int:
    """The staff nav's Reports count: returned reports, and for a head also the reports waiting
    for their review or approved and not sent yet (rev 33). The office counts sent ones only."""
    statuses = [Report.Status.RETURNED]
    if head:
        statuses += [Report.Status.WITH_HEAD, Report.Status.APPROVED]
    rows = _sent() if office else Report.objects.all()
    return rows.filter(program=program, status__in=statuses).count()


def head_counts(program: Program) -> tuple[int, int]:
    """(waiting for the head, approved and not sent) in one query."""
    counts = Report.objects.filter(program=program).aggregate(
        waiting=Count("pk", filter=Q(status=Report.Status.WITH_HEAD)),
        approved=Count("pk", filter=Q(status=Report.Status.APPROVED)),
    )
    return counts["waiting"], counts["approved"]


def oldest_submitted() -> datetime | None:
    """When the longest-waiting report to review was sent to the office."""
    value: datetime | None = Report.objects.filter(status=Report.Status.SUBMITTED).aggregate(
        oldest=Min("sent_at")
    )["oldest"]
    return value


def status_counts(program: Program | None, *, office: bool = False) -> dict[str, int]:
    """Reports per status, and "all", for one program or (None) every program; the office
    counts only the reports sent to it."""
    rows = _sent() if office else Report.objects.all()
    if program is not None:
        rows = rows.filter(program=program)
    counts = {
        row["status"]: row["n"] for row in rows.values("status").order_by().annotate(n=Count("pk"))
    }
    counts["all"] = sum(counts.values())
    return counts
