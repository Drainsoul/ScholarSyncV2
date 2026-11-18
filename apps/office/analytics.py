"""Office analytics and the program summary (spec §12, M11c).

Figures count new applications only (`kind=new`), ever submitted, whose term is in the school
year. Renewals would inflate the success rate. Queries are a fixed number whatever the number of
programs."""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, QuerySet, Sum
from django.http import QueryDict

from apps.applications.models import Application
from apps.applications.review_selectors import applications_by_month
from apps.awards.models import ScholarTerm
from apps.awards.selectors import active_counts
from apps.awards.tabular import write_csv, write_xlsx
from apps.core.charts import MonthBar, first_month, month_bars
from apps.core.params import positive_id
from apps.files.policy import XLSX
from apps.money.models import Disbursement
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import current_term

MONTHS = 12
TOP_SCHOOLS = 10
DASH = "—"
SUMMARY_HEADERS = (
    "Program",
    "School year",
    "Applications",
    "Approved",
    "Not approved",
    "Success rate",
    "Median days to approve",
    "Active scholars (now)",
    "Released",
)
CSV_TYPE = "text/csv; charset=utf-8"


@dataclass(frozen=True)
class AnalyticsFilters:
    year: int | None
    program: Program | None


@dataclass(frozen=True)
class ProgramRow:
    program: Program
    applications: int
    approved: int
    rejected: int
    success_percent: int | None
    median_days: Decimal | None
    active_scholars: int
    released: Decimal


@dataclass(frozen=True)
class Analytics:
    figures: list[dict[str, str]]
    months: list[MonthBar]
    rows: list[ProgramRow]
    schools: list[dict[str, object]]
    unlisted: int


def school_years() -> list[int]:
    """Every school year that has terms, newest first."""
    return list(
        AcademicTerm.objects.order_by("-school_year_start")
        .values_list("school_year_start", flat=True)
        .distinct()
    )


def default_year(years: list[int]) -> int | None:
    term = current_term()
    if term is not None:
        return term.school_year_start
    return years[0] if years else None


def parse_analytics_filters(params: QueryDict) -> AnalyticsFilters:
    """Unknown values fall back to the defaults, never an error."""
    years = school_years()
    year = positive_id(params.get("year", ""))
    if year not in years:
        year = default_year(years)
    program_id = positive_id(params.get("program", ""))
    program = Program.objects.filter(pk=program_id).first() if program_id is not None else None
    return AnalyticsFilters(year=year, program=program)


def success_percent(approved: int, rejected: int) -> int | None:
    """Approved ÷ (approved + rejected), a whole percent rounded half up; None with no decisions."""
    decided = approved + rejected
    if not decided:
        return None
    return int((Decimal(approved * 100) / decided).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def median_days(durations: list[timedelta]) -> Decimal | None:
    """The median duration in days, one decimal, rounded half up; None for no durations."""
    if not durations:
        return None
    middle = statistics.median(duration.total_seconds() for duration in durations)
    return (Decimal(str(middle)) / 86400).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _counted(year: int | None, program: Program | None) -> QuerySet[Application]:
    rows = Application.objects.filter(kind=Application.Kind.NEW, first_submitted_at__isnull=False)
    rows = rows.filter(term__school_year_start=year) if year is not None else rows.none()
    if program is not None:
        rows = rows.filter(program=program)
    return rows


def _durations(counted: QuerySet[Application]) -> list[tuple[int, timedelta]]:
    """(program id, days from first submission to approval) for each approved application."""
    result = []
    for program_id, sent, decided in counted.filter(
        status=Application.Status.APPROVED, decided_at__isnull=False
    ).values_list("program_id", "first_submitted_at", "decided_at"):
        if sent is not None and decided is not None:
            result.append((program_id, decided - sent))
    return result


def _rows(year: int | None, program: Program | None) -> list[ProgramRow]:
    """One row per program: the chosen one, or every open program plus any with applications,
    scholars or released money in the year (a closed program keeps its row)."""
    counted = _counted(year, program)
    totals: dict[int, dict[str, int]] = {
        row["program_id"]: {
            "applications": row["applications"],
            "approved": row["approved"],
            "rejected": row["rejected"],
        }
        for row in counted.values("program_id")
        .order_by()
        .annotate(
            applications=Count("pk"),
            approved=Count("pk", filter=Q(status=Application.Status.APPROVED)),
            rejected=Count("pk", filter=Q(status=Application.Status.REJECTED)),
        )
    }
    durations: dict[int, list[timedelta]] = {}
    for program_id, duration in _durations(counted):
        durations.setdefault(program_id, []).append(duration)
    released: dict[int, Decimal] = {}
    held: set[int] = set()
    if year is not None:
        payouts = Disbursement.objects.filter(
            status=Disbursement.Status.RELEASED, scholar_term__term__school_year_start=year
        )
        records = ScholarTerm.objects.filter(term__school_year_start=year)
        if program is not None:
            payouts = payouts.filter(scholar_term__award__program=program)
            records = records.filter(award__program=program)
        released = {
            row["scholar_term__award__program_id"]: row["total"]
            for row in payouts.values("scholar_term__award__program_id")
            .order_by()
            .annotate(total=Sum("amount"))
        }
        held = set(records.values_list("award__program_id", flat=True).distinct())
    if program is not None:
        programs = [program]
    else:
        # Every open program, and any program with applications, scholars or money in the year.
        ids_in_year = {*totals, *released, *held}
        programs = list(
            Program.objects.filter(Q(is_active=True) | Q(pk__in=ids_in_year)).order_by("name")
        )
    scholars = active_counts([item.pk for item in programs])
    result = []
    for item in programs:
        total: dict[str, int] = totals.get(item.pk, {})
        approved, rejected = total.get("approved", 0), total.get("rejected", 0)
        result.append(
            ProgramRow(
                program=item,
                applications=total.get("applications", 0),
                approved=approved,
                rejected=rejected,
                success_percent=success_percent(approved, rejected),
                median_days=median_days(durations.get(item.pk, [])),
                active_scholars=scholars.get(item.pk, 0),
                released=released.get(item.pk, Decimal("0.00")),
            )
        )
    return result


def _schools(year: int | None, program: Program | None) -> tuple[list[dict[str, object]], int]:
    counted = _counted(year, program)
    top = (
        counted.filter(school__isnull=False)
        .values("school_id", "school__name")
        .order_by()
        .annotate(
            applications=Count("pk"),
            approved=Count("pk", filter=Q(status=Application.Status.APPROVED)),
        )
        .order_by("-approved", "-applications", "school__name")[:TOP_SCHOOLS]
    )
    schools: list[dict[str, object]] = [
        {
            "name": row["school__name"],
            "applications": row["applications"],
            "approved": row["approved"],
        }
        for row in top
    ]
    return schools, counted.filter(school__isnull=True).count()


def _figure(value: object) -> str:
    return DASH if value is None else str(value)


def analytics(filters: AnalyticsFilters, *, today: date) -> Analytics:
    rows = _rows(filters.year, filters.program)
    applications = sum(row.applications for row in rows)
    approved = sum(row.approved for row in rows)
    rejected = sum(row.rejected for row in rows)
    durations = [
        duration for _program, duration in _durations(_counted(filters.year, filters.program))
    ]
    rate = success_percent(approved, rejected)
    figures = [
        {"label": "Applications", "value": f"{applications:,}"},
        {"label": "Approved", "value": f"{approved:,}"},
        {"label": "Success rate", "value": DASH if rate is None else f"{rate}%"},
        {"label": "Median days to approve", "value": _figure(median_days(durations))},
    ]
    trend_programs = (
        [filters.program] if filters.program is not None else list(Program.objects.all())
    )
    months = month_bars(
        applications_by_month(trend_programs, since=first_month(today, MONTHS)),
        today=today,
        months=MONTHS,
    )
    schools, unlisted = _schools(filters.year, filters.program)
    return Analytics(figures=figures, months=months, rows=rows, schools=schools, unlisted=unlisted)


def summary_file(year: int | None, fmt: str) -> tuple[bytes, str, str, int]:
    """(body, content type, filename, row count): one row per program for the school year."""
    label = f"{year}–{year + 1}" if year is not None else ""
    rows: list[list[object]] = [
        [
            row.program.name,
            label,
            row.applications,
            row.approved,
            row.rejected,
            row.success_percent,
            row.median_days,
            row.active_scholars,
            row.released,
        ]
        for row in _rows(year, None)
    ]
    if fmt == "xlsx":
        body, content_type = write_xlsx(SUMMARY_HEADERS, rows), XLSX
    else:
        fmt = "csv"
        body, content_type = write_csv(SUMMARY_HEADERS, rows), CSV_TYPE
    suffix = f"{year}-{year + 1}" if year is not None else "none"
    return body, content_type, f"program-summary-{suffix}.{fmt}", len(rows)
