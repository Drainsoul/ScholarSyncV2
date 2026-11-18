"""Office analytics and the program summary (M11c)."""

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.tests.factories import RenewalFactory
from apps.core.models import AuditEvent
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import ScheduleFactory
from apps.office.analytics import median_days, success_percent
from apps.programs.models import AcademicTerm, Program
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory, SchoolFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=TZ)
PAGE = "/office/analytics/"
EXPORT = "/office/analytics/export/"
S = Application.Status


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _app(
    program: Program,
    term: AcademicTerm,
    status: str,
    *,
    days: int | None = None,
    sent_days_ago: int = 30,
    **kwargs: Any,
) -> Application:
    sent = NOW - timedelta(days=sent_days_ago)
    decided = sent + timedelta(days=days) if days is not None else None
    if status in (S.APPROVED, S.REJECTED) and decided is None:
        decided = sent + timedelta(days=1)
    return ApplicationFactory.create(
        program=program,
        term=term,
        status=status,
        submitted_at=sent,
        first_submitted_at=sent,
        decided_at=decided,
        **kwargs,
    )


@pytest.fixture
def world() -> dict[str, Any]:
    """A worked example for SY 2026–2027."""
    term = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    old = AcademicTermFactory.create(school_year_start=2025, term=2)
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    near, far = SchoolFactory.create(name="Taguig High"), SchoolFactory.create(name="Bonifacio U")
    for n, days in enumerate((2, 3, 3, 4, 5, 10)):
        _app(tcu, term, S.APPROVED, days=days, school=near if n < 4 else far)
    _app(tcu, term, S.REJECTED, school=far)
    _app(tcu, term, S.REJECTED, school=far)
    _app(tcu, term, S.WITHDRAWN)
    _app(tcu, term, S.UNDER_REVIEW)
    for _ in range(3):
        sent = NOW - timedelta(days=30)
        RenewalFactory.create(
            award__source_application__program=tcu,
            term=term,
            status=S.APPROVED,
            submitted_at=sent,
            first_submitted_at=sent,
            decided_at=sent + timedelta(days=1),
        )
    _app(lani, term, S.UNDER_REVIEW)
    _app(lani, term, S.UNDER_REVIEW)
    _app(tcu, old, S.APPROVED, days=30)  # another school year
    ApplicationFactory.create(program=tcu, term=term)  # a draft never submitted
    return {"term": term, "tcu": tcu, "lani": lani}


def test_success_percent_rounding() -> None:
    assert success_percent(2, 1) == 67
    assert success_percent(1, 1) == 50
    assert success_percent(6, 2) == 75
    assert success_percent(0, 0) is None


def test_median_days() -> None:
    days = [timedelta(days=n) for n in (2, 3, 3, 4, 5, 10)]
    assert median_days(days) == Decimal("3.5")
    assert median_days([timedelta(hours=36)]) == Decimal("1.5")
    assert median_days([]) is None


def test_figures(client: Any, office: User, world: dict[str, Any]) -> None:
    board = client.get(PAGE).context["board"]
    assert board.figures == [
        {"label": "Applications", "value": "12"},
        {"label": "Approved", "value": "6"},
        {"label": "Success rate", "value": "75%"},
        {"label": "Median days to approve", "value": "3.5"},
    ]
    assert "New applications only." in client.get(PAGE).content.decode()


def test_by_program_rows(client: Any, office: User, world: dict[str, Any]) -> None:
    rows = client.get(PAGE).context["board"].rows
    by_name = {row.program.name: row for row in rows}
    tcu, lani = by_name["TCU CEAA"], by_name["LANI"]
    assert (tcu.applications, tcu.approved, tcu.rejected) == (10, 6, 2)
    assert (tcu.success_percent, tcu.median_days) == (75, Decimal("3.5"))
    assert (lani.applications, lani.approved, lani.rejected) == (2, 0, 0)
    assert (lani.success_percent, lani.median_days) == (None, None)
    html = client.get(PAGE).content.decode()
    assert "—" in html


def test_top_schools_order_and_unlisted_note(
    client: Any, office: User, world: dict[str, Any]
) -> None:
    board = client.get(PAGE).context["board"]
    assert [(row["name"], row["applications"], row["approved"]) for row in board.schools] == [
        ("Taguig High", 4, 4),
        ("Bonifacio U", 4, 2),
    ]
    assert board.unlisted == 4
    assert (
        "4 applications named a school that isn't on the list." in client.get(PAGE).content.decode()
    )


def test_trend_is_12_months_zero_filled(client: Any, office: User, world: dict[str, Any]) -> None:
    months = client.get(PAGE).context["board"].months
    assert len(months) == 12
    assert months[-1].label == "November 2026"
    assert months[0].label == "December 2025"
    assert sum(month.count for month in months) == 16  # every kind and year, ever submitted


def test_program_filter(client: Any, office: User, world: dict[str, Any]) -> None:
    board = client.get(PAGE + f"?program={world['lani'].pk}").context["board"]
    assert board.figures[0] == {"label": "Applications", "value": "2"}
    assert [row.program.name for row in board.rows] == ["LANI"]


def test_filters_fall_back(client: Any, office: User, world: dict[str, Any]) -> None:
    response = client.get(PAGE + "?year=abc&program=999")
    assert response.status_code == 200
    assert response.context["filters"].year == 2026
    assert response.context["filters"].program is None
    assert client.get(PAGE + "?year=2025").context["filters"].year == 2025
    assert client.get(PAGE + "?year=1990").context["filters"].year == 2026


def test_no_terms_at_all_answers_200(client: Any, office: User) -> None:
    ProgramFactory.create(name="Empty")
    response = client.get(PAGE)
    assert response.status_code == 200
    assert response.context["board"].figures[2] == {"label": "Success rate", "value": "—"}
    assert client.get(EXPORT).status_code == 200


def test_queries_do_not_grow_with_programs(client: Any, office: User) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    term = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)

    def count() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert client.get(PAGE).status_code == 200
        return len(queries)

    for program in ProgramFactory.create_batch(2):
        _app(program, term, S.APPROVED, days=2)
    two = count()
    for program in ProgramFactory.create_batch(4):
        _app(program, term, S.APPROVED, days=2)
    assert count() == two


def test_summary_csv_xlsx_columns_and_audit(
    client: Any, office: User, world: dict[str, Any]
) -> None:
    schedule = ScheduleFactory.create(program=world["tcu"], term=world["term"])
    payout(schedule, status=Disbursement.Status.RELEASED, amount=Decimal("5000.00"))
    payout(schedule, status=Disbursement.Status.APPROVED, amount=Decimal("7000.00"))
    old_schedule = ScheduleFactory.create(
        program=world["tcu"], term=AcademicTerm.objects.get(school_year_start=2025)
    )
    payout(old_schedule, status=Disbursement.Status.RELEASED, amount=Decimal("9000.00"))
    response = client.get(EXPORT + "?year=2026&format=csv")
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Disposition"] == (
        'attachment; filename="program-summary-2026-2027.csv"'
    )
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == [
        "Program",
        "School year",
        "Applications",
        "Approved",
        "Not approved",
        "Success rate",
        "Median days to approve",
        "Active scholars",
        "Released",
    ]
    tcu = next(row for row in rows if row[0] == "TCU CEAA")
    assert tcu[1:7] == ["2026–2027", "10", "6", "2", "75", "3.5"]
    assert tcu[8] == "5000.00"
    lani = next(row for row in rows if row[0] == "LANI")
    assert lani[5:7] == ["", ""]
    event = AuditEvent.objects.get(action="analytics.exported")
    assert event.data == {"format": "csv", "year": 2026, "rows": len(rows) - 1}
    sheet = load_workbook(io.BytesIO(client.get(EXPORT + "?year=2026").content)).active
    assert sheet is not None
    assert sheet.cell(row=1, column=1).value == "Program"


def test_overview_download_report_links_to_current_year_xlsx(
    client: Any, office: User, world: dict[str, Any]
) -> None:
    html = client.get(reverse("office:home")).content.decode()
    assert "Download report" in html
    assert f'href="{EXPORT}?year=2026&amp;format=xlsx"' in html


def test_analytics_nav_item(client: Any, office: User) -> None:
    labels = [item["label"] for item in client.get(PAGE).context["nav_items"]]
    assert labels == [
        "Overview",
        "Programs",
        "Staff",
        "Scholars",
        "Schools",
        "Terms",
        "Reports",
        "Analytics",
        "Audit log",
        "Support",
    ]


def test_summary_keeps_a_closed_program_with_money_in_the_year(
    client: Any, office: User, world: dict[str, Any]
) -> None:
    closed = ProgramFactory.create(name="Old Grant", is_active=False)
    schedule = ScheduleFactory.create(program=closed, term=world["term"])
    payout(schedule, status=Disbursement.Status.RELEASED, amount=Decimal("3000.00"))
    response = client.get(EXPORT + "?year=2026&format=csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    old = next(row for row in rows if row[0] == "Old Grant")
    assert old[8] == "3000.00"
