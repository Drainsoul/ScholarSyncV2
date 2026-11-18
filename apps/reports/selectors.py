"""Report reads (spec §4.8, M11c)."""

from datetime import datetime

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Min, QuerySet
from django.http import Http404

from apps.accounts.models import User
from apps.core.permissions import require_program_staff
from apps.files.models import StoredFile
from apps.programs.models import Program

from .models import Report, ReportFile

REPORT_TABS_STAFF = {
    "all": "All",
    "submitted": "Waiting",
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
    try:
        require_program_staff(user, row.report.program)
    except PermissionDenied:
        return False
    return True


def program_reports(program: Program, tab: str) -> QuerySet[Report]:
    """The program's reports for a staff tab, newest first; an unknown tab is All."""
    rows = Report.objects.filter(program=program).select_related("program")
    if tab in Report.Status.values:
        rows = rows.filter(status=tab)
    return rows.order_by("-submitted_at", "-pk")


def office_reports(tab: str, program_id: int | None) -> QuerySet[Report]:
    """Every program's reports for an office tab: To review oldest first, the rest newest first."""
    rows = Report.objects.select_related("program")
    if program_id is not None:
        rows = rows.filter(program_id=program_id)
    if tab in Report.Status.values:
        rows = rows.filter(status=tab)
    if tab == Report.Status.SUBMITTED:
        return rows.order_by("submitted_at", "pk")
    return rows.order_by("-submitted_at", "-pk")


def staff_report(program: Program, pk: int) -> Report:
    """One of the program's reports with its files; another program's id is a 404."""
    report = (
        Report.objects.filter(program=program, pk=pk)
        .select_related("program", "submitted_by", "reviewed_by")
        .first()
    )
    if report is None:
        raise Http404("No such report.")
    return report


def office_report(pk: int) -> Report:
    report = (
        Report.objects.filter(pk=pk)
        .select_related("program", "submitted_by", "reviewed_by")
        .first()
    )
    if report is None:
        raise Http404("No such report.")
    return report


def report_files(report: Report) -> QuerySet[ReportFile]:
    return report.files.select_related("file").order_by("-created_at", "-pk")


def submitted_count() -> int:
    return Report.objects.filter(status=Report.Status.SUBMITTED).count()


def returned_count(program: Program) -> int:
    return Report.objects.filter(program=program, status=Report.Status.RETURNED).count()


def oldest_submitted() -> datetime | None:
    value: datetime | None = Report.objects.filter(status=Report.Status.SUBMITTED).aggregate(
        oldest=Min("submitted_at")
    )["oldest"]
    return value


def status_counts(program: Program | None) -> dict[str, int]:
    """Reports per status, and "all", for one program or (None) every program."""
    rows = Report.objects.all() if program is None else Report.objects.filter(program=program)
    counts = {
        row["status"]: row["n"] for row in rows.values("status").order_by().annotate(n=Count("pk"))
    }
    counts["all"] = sum(counts.values())
    return counts
