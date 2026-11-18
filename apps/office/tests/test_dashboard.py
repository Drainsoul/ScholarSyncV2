from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award
from apps.awards.tests.factories import AwardFactory
from apps.core.audit import record
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import BudgetFactory, ScheduleFactory
from apps.office.dashboard import office_dashboard
from apps.programs.models import Program
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 9, 30, tzinfo=TZ)
S = Application.Status


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


@pytest.fixture
def office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, full_name="Jessica Tate")


def _waiting(program: Program, days: int, **kwargs: Any) -> Application:
    sent = NOW - timedelta(days=days)
    return ApplicationFactory.create(
        program=program, status=S.SUBMITTED, submitted_at=sent, first_submitted_at=sent, **kwargs
    )


def _used(program: Program, percent: int) -> None:
    """A 2026 budget of ₱100,000 with `percent` of it approved."""
    BudgetFactory.create(program=program, fiscal_year=2026, amount=Decimal("100000.00"))
    schedule = ScheduleFactory.create(program=program, distribution_date=date(2026, 9, 15))
    payout(schedule, status=Disbursement.Status.APPROVED, amount=Decimal(percent * 1000))


@pytest.mark.parametrize(
    ("hour", "minute", "word"),
    [(11, 59, "morning"), (12, 0, "afternoon"), (17, 59, "afternoon"), (18, 0, "evening")],
)
def test_greeting_by_manila_hour(office: User, hour: int, minute: int, word: str) -> None:
    now = datetime(2026, 11, 17, hour, minute, tzinfo=TZ).astimezone(UTC)
    assert office_dashboard(office, now=now).greeting == f"Good {word}, Jessica"


def test_figures_across_programs(office: User) -> None:
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    second = AcademicTermFactory.create(school_year_start=2026, term=2)
    old = AcademicTermFactory.create(school_year_start=2025, term=2)
    tcu, lani = ProgramFactory.create_batch(2)
    AwardFactory.create_batch(2, source_application__program=tcu)
    AwardFactory.create(source_application__program=lani)
    AwardFactory.create(source_application__program=lani, status=Award.Status.GRADUATED)
    _waiting(tcu, 9, term=current)
    _waiting(lani, 8, term=second)
    _waiting(lani, 1, term=old)
    ApplicationFactory.create(program=tcu, term=current)  # a draft
    figures = office_dashboard(office, now=NOW).figures
    assert figures[:3] == [
        {"label": "Scholars", "value": "3"},
        {"label": "Applications", "value": "2"},
        {"label": "Waiting over 7 days", "value": "2"},
    ]
    current.is_current = False
    current.save()
    assert office_dashboard(office, now=NOW).figures[1] == {"label": "Applications", "value": "0"}


def test_attention_per_program_and_budget_threshold(office: User) -> None:
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    quiet = ProgramFactory.create(name="Quiet")
    _waiting(tcu, 9)
    _waiting(tcu, 10)
    _waiting(lani, 8)
    _used(tcu, 75)
    _used(lani, 74)
    _ = quiet  # no budget: no row
    rows = office_dashboard(office, now=NOW).attention
    assert [(row["title"], row["tone"]) for row in rows] == [
        ("1 LANI application has waited more than 7 days", "danger"),
        ("2 TCU CEAA applications have waited more than 7 days", "danger"),
        ("TCU CEAA has used 75% of its budget", "warning"),
    ]
    assert rows[1]["url"] == reverse("review:queue", kwargs={"program": tcu.slug})
    assert rows[1]["detail"] == "Oldest sent 10 days ago"
    assert rows[2]["url"] == reverse("money:budget", kwargs={"program": tcu.slug})


def test_programs_table_window_text(office: User) -> None:
    today = NOW.date()
    ProgramFactory.create(name="A closed", applications_close_on=today - timedelta(1))
    ProgramFactory.create(name="B until", applications_close_on=date(2026, 12, 15))
    ProgramFactory.create(name="C later", applications_open_on=date(2027, 1, 5))
    ProgramFactory.create(name="D open")
    ProgramFactory.create(name="E inactive", is_active=False)
    rows = office_dashboard(office, now=NOW).programs
    assert [(row["name"], row["window"]) for row in rows] == [
        ("A closed", "Applications closed"),
        ("B until", "Open until 15 December"),
        ("C later", "Opens on 5 January"),
        ("D open", "Open"),
    ]
    assert rows[0]["used_percent"] is None


def test_dropped_mockup_parts_absent(client: Any, office: User) -> None:
    ProgramFactory.create(name="TCU CEAA")
    client.force_login(office)
    html = client.get(reverse("office:home")).content.decode()
    assert "Good morning, Jessica" in html
    for text in ("New program", "Manage programs"):
        assert text not in html
    assert 'href="#"' not in html
    for text in ("Applications by month", "Needs attention", "Programs", "Recent activity"):
        assert text in html


def test_recent_activity_latest_eight(client: Any, office: User) -> None:
    program = ProgramFactory.create(name="LANI")
    staff = UserFactory.create(role=User.Role.STAFF, full_name="Shannon Briggs")
    for _ in range(9):
        record(actor=staff, action="schedule.published", program=program)
    client.force_login(office)
    html = client.get(reverse("office:home")).content.decode()
    assert html.count("Shannon Briggs published a distribution day (LANI)") == 8
    assert "Today, 9:30 AM" in html


def test_overview_query_count(
    client: Any, office: User, django_assert_max_num_queries: Any
) -> None:
    tcu, lani = ProgramFactory.create_batch(2)
    for program in (tcu, lani):
        AwardFactory.create_batch(25, source_application__program=program)
        for n in range(10):
            _waiting(program, n + 3)
    staff = UserFactory.create(role=User.Role.STAFF)
    for _ in range(50):
        record(actor=staff, action="award.created", program=tcu)
    client.force_login(office)
    with django_assert_max_num_queries(25):
        assert client.get(reverse("office:home")).status_code == 200


def test_overview_queries_do_not_grow_with_programs(client: Any, office: User) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(office)

    def count() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert client.get(reverse("office:home")).status_code == 200
        return len(queries)

    for program in ProgramFactory.create_batch(2):
        _used(program, 10)
    two = count()
    for program in ProgramFactory.create_batch(4):
        _used(program, 10)
    assert count() == two


def test_overview_reports_figure_and_attention_row(office: User) -> None:
    from apps.reports.tests.factories import ReportFactory

    for days in (4, 2, 0):
        ReportFactory.create(submitted_at=NOW - timedelta(days=days))
    ReportFactory.create(status="accepted", submitted_at=NOW - timedelta(days=30))
    board = office_dashboard(office, now=NOW)
    assert board.figures[3] == {"label": "Reports to review", "value": "3"}
    assert board.attention[0] == {
        "title": "3 program reports are waiting for your review",
        "detail": "Oldest sent 4 days ago",
        "tone": "warning",
        "url": reverse("office:reports"),
    }


def test_overview_single_report_sent_today(office: User) -> None:
    from apps.reports.tests.factories import ReportFactory

    ReportFactory.create(submitted_at=NOW - timedelta(hours=1))
    row = office_dashboard(office, now=NOW).attention[0]
    assert row["title"] == "1 program report is waiting for your review"
    assert row["detail"] == "Sent today"


def test_overview_has_no_support_figure(office: User) -> None:
    labels = [figure["label"] for figure in office_dashboard(office, now=NOW).figures]
    assert labels == ["Scholars", "Applications", "Waiting over 7 days", "Reports to review"]


def test_exactly_seven_days_is_not_waiting_over_seven() -> None:
    from apps.applications.review_selectors import waiting_over
    from apps.applications.tests.factories import ApplicationFactory as _Applications

    application = _Applications.create(status="submitted", submitted_at=NOW - timedelta(days=7))
    assert waiting_over([application.program_id], days=7, now=NOW) == {}
    older = _Applications.create(
        program=application.program,
        status="submitted",
        submitted_at=NOW - timedelta(days=7, seconds=1),
    )
    assert waiting_over([application.program_id], days=7, now=NOW) == {
        application.program_id: (1, older.submitted_at)
    }


def test_greeting_without_a_name() -> None:
    from apps.office.dashboard import greeting

    nameless = UserFactory.create(role=User.Role.SUPER_ADMIN, full_name="")
    now = datetime(2026, 11, 17, 9, 0, tzinfo=TZ)
    assert greeting(nameless, now) == "Good morning"
