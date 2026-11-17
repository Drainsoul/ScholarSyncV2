"""The scholar list as a file: the filtered list's rows under fixed headers (spec §7, M9b).

Birth dates are left out (data minimisation, RA 10173). Strings are neutralised against formulas
by the table writers."""

from collections.abc import Iterator
from datetime import date

from django.db.models import QuerySet

from apps.awards.models import Award
from apps.awards.selectors import ScholarFilters, scholars
from apps.awards.tabular import write_csv, write_xlsx
from apps.files.policy import XLSX
from apps.programs.models import AcademicTerm, Program, School

HEADERS: tuple[str, ...] = (
    "Last name",
    "First name",
    "Middle name",
    "Suffix",
    "Student number",
    "Tier",
    "Status",
    "Started",
    "School",
    "Course",
    "Year level",
    "GWA",
    "Grading scale",
    "Units",
    "Terms recorded",
    "Account",
)
FORMATS = ("csv", "xlsx")
CSV_TYPE = "text/csv; charset=utf-8"


def _scale_label(value: str | None) -> str | None:
    if not value or value not in School.Scale.values:
        return None
    return str(School.Scale(value).label)


def export_rows(rows: QuerySet[Award]) -> Iterator[list[object]]:
    """One row per award; `rows` comes from `scholars()` (annotated with its latest term)."""
    for award in rows.iterator(chunk_size=500):
        profile = award.profile
        yield [
            profile.last_name,
            profile.first_name,
            profile.middle_name or None,
            profile.suffix or None,
            award.student_number or None,
            award.tier.code,
            award.get_status_display(),
            str(award.started_term),
            award.latest_school_name or None,  # type: ignore[attr-defined]
            award.latest_course or None,  # type: ignore[attr-defined]
            award.latest_year_level,  # type: ignore[attr-defined]
            award.latest_gwa,  # type: ignore[attr-defined]
            _scale_label(award.latest_gwa_scale),  # type: ignore[attr-defined]
            award.latest_units,  # type: ignore[attr-defined]
            award.term_count,  # type: ignore[attr-defined]
            "Claimed" if profile.user_id is not None else "Not claimed",
        ]


def export_file(
    program: Program,
    filters: ScholarFilters,
    fmt: str,
    *,
    term: AcademicTerm | None,
    today: date,
) -> tuple[bytes, str, str, int]:
    """(body, content type, filename, row count) for the filtered list in `fmt` (csv or xlsx;
    anything else is csv)."""
    rows = list(export_rows(scholars(program, filters, term=term, today=today)))
    if fmt == "xlsx":
        body, content_type = write_xlsx(HEADERS, rows), XLSX
    else:
        fmt = "csv"
        body, content_type = write_csv(HEADERS, rows), CSV_TYPE
    filename = f"scholars-{program.slug}-{filters.status}-{today.isoformat()}.{fmt}"
    return body, content_type, filename, len(rows)
