from datetime import date, datetime, timedelta
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
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import AcademicTermFactory, MembershipFactory, ProgramFactory
from apps.workspace.dashboard import staff_dashboard
from apps.workspace.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
S = Application.Status


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


def _staff(program: Program) -> User:
    return MembershipFactory.create(program=program).user


def _waiting(program: Program, days: int, status: str = S.SUBMITTED, **kwargs: Any) -> Application:
    sent = NOW - timedelta(days=days)
    kwargs.setdefault("first_submitted_at", sent)
    return ApplicationFactory.create(program=program, status=status, submitted_at=sent, **kwargs)


def _titles(rows: list[dict[str, str]]) -> list[str]:
    return [row["title"] for row in rows]


def test_applications_by_month_buckets_in_manila() -> None:
    program = ProgramFactory.create()
    late_october = datetime(2026, 10, 31, 23, 30, tzinfo=TZ)
    early_november = datetime(2026, 11, 1, 0, 10, tzinfo=TZ)
    for sent in (late_october, early_november):
        ApplicationFactory.create(
            program=program, status=S.APPROVED, submitted_at=sent, first_submitted_at=sent
        )
    ApplicationFactory.create(program=program)  # a draft: never submitted
    months = staff_dashboard(program, _staff(program), now=NOW).months
    assert [(bar.short, bar.count) for bar in months] == [
        ("Jun", 0),
        ("Jul", 0),
        ("Aug", 0),
        ("Sep", 0),
        ("Oct", 1),
        ("Nov", 1),
    ]


def test_figures() -> None:
    program = ProgramFactory.create(renewal_min_gwa_percent=Decimal("80"))
    AwardFactory.create_batch(2, source_application__program=program)
    AwardFactory.create(source_application__program=program, status=Award.Status.SUSPENDED)
    risky = AwardFactory.create(source_application__program=program)
    ScholarTermFactory.create(award=risky, gwa=Decimal("75"), gwa_scale="percent")
    _waiting(program, 1)
    _waiting(program, 2, S.UNDER_REVIEW)
    _waiting(program, 3, S.RETURNED)
    this_year = ScheduleFactory.create(program=program, distribution_date=date(2026, 3, 1))
    payout(this_year, status=Disbursement.Status.RELEASED, amount=Decimal("5000.00"))
    payout(this_year, status=Disbursement.Status.APPROVED, amount=Decimal("9000.00"))
    last_year = ScheduleFactory.create(program=program, distribution_date=date(2025, 12, 1))
    payout(last_year, status=Disbursement.Status.RELEASED, amount=Decimal("7000.00"))
    figures = staff_dashboard(program, _staff(program), now=NOW).figures
    assert figures == [
        {"label": "Active scholars", "value": "6"},  # 3 here + 3 payout scholars
        {"label": "Applications waiting", "value": "2"},
        {"label": "Released this year", "value": "₱5,000.00"},
        {"label": "At risk", "value": "1"},
    ]


def test_attention_rows_in_order_with_plurals() -> None:
    program = ProgramFactory.create(renewal_min_gwa_percent=Decimal("80"))
    user = _staff(program)
    _waiting(program, 9)
    _waiting(program, 3)
    TaskFactory.create(owner=user, program=program, due_on=TODAY - timedelta(1))
    risky = AwardFactory.create(source_application__program=program)
    ScholarTermFactory.create(award=risky, gwa=Decimal("75"), gwa_scale="percent")
    schedule = ScheduleFactory.create(program=program)
    payout(schedule)
    payout(schedule)
    payout(schedule, status=Disbursement.Status.APPROVED)
    hidden = ScheduleFactory.create(program=program, is_published=False)
    payout(hidden)
    rows = staff_dashboard(program, user, now=NOW).attention
    slug = program.slug
    assert rows == [
        {
            "title": "1 application has waited more than 7 days",
            "detail": "Oldest sent 9 days ago",
            "tone": "danger",
            "url": reverse("review:queue", kwargs={"program": slug}),
        },
        {
            "title": "1 of your tasks is overdue",
            "detail": "Open your task list",
            "tone": "danger",
            "url": reverse("workspace:tasks", kwargs={"program": slug}),
        },
        {
            "title": "1 scholar is at risk",
            "detail": "Check their grades and renewals",
            "tone": "warning",
            "url": reverse("scholars:list", kwargs={"program": slug}) + "?status=at_risk",
        },
        {
            "title": "2 payouts are prepared and waiting for a head",
            "detail": "A head approves them in Disbursements",
            "tone": "warning",
            "url": reverse("money:overview", kwargs={"program": slug}),
        },
        {
            "title": "1 approved payout is ready to release",
            "detail": "Release it on or after the distribution day",
            "tone": "info",
            "url": reverse("money:overview", kwargs={"program": slug}),
        },
    ]


def test_resubmission_restarts_the_wait() -> None:
    program = ProgramFactory.create()
    _waiting(program, 2, first_submitted_at=NOW - timedelta(days=30))
    titles = _titles(staff_dashboard(program, _staff(program), now=NOW).attention)
    assert not any("waited" in title for title in titles)


def test_window_rows() -> None:
    later = ProgramFactory.create(applications_open_on=date(2026, 11, 20))
    closing = ProgramFactory.create(applications_close_on=TODAY + timedelta(10))
    far = ProgramFactory.create(applications_close_on=TODAY + timedelta(20))
    row = staff_dashboard(later, _staff(later), now=NOW).attention[0]
    assert (row["title"], row["detail"], row["tone"]) == (
        "Applications open on 20 November",
        "Starts in 3 days",
        "info",
    )
    assert row["url"] == reverse("programs:detail", kwargs={"slug": later.slug})
    row = staff_dashboard(closing, _staff(closing), now=NOW).attention[0]
    assert (row["title"], row["detail"], row["tone"]) == (
        "Applications close on 27 November",
        "Ends in 10 days",
        "warning",
    )
    assert staff_dashboard(far, _staff(far), now=NOW).attention == []


def test_nothing_needs_attention_empty_state(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    html = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug})).content
    assert "Nothing needs attention right now." in html.decode()
    assert "No open tasks." in html.decode()


def test_your_tasks_shows_only_own_open_tasks(client: Any) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(owner=user, program=program, title="Mine to do")
    TaskFactory.create(owner=user, program=program, title="Mine done", done_at=NOW)
    TaskFactory.create(owner=_staff(program), program=program, title="Someone else's")
    for n in range(6):
        TaskFactory.create(
            owner=user, program=program, title=f"Later {n}", due_on=TODAY + timedelta(n + 1)
        )
    board = staff_dashboard(program, user, now=NOW)
    assert len(board.tasks) == 5
    assert all(task.owner == user and task.done_at is None for task in board.tasks)
    client.force_login(user)
    html = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug})).content
    assert "Someone else" not in html.decode()
    assert "Mine done" not in html.decode()


@pytest.mark.parametrize("who", ["head", "office"])
def test_dashboard_page_renders_for_office_and_head(client: Any, who: str) -> None:
    program = ProgramFactory.create()
    AcademicTermFactory.create(is_current=True)
    _waiting(program, 9)
    if who == "head":
        user = MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user
    else:
        user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    response = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug}))
    html = response.content.decode()
    assert response.status_code == 200
    for text in ("Active scholars", "Needs attention", "Applications by month", "Your tasks"):
        assert text in html
    assert "View as table" in html
    assert 'data-percent="100"' in html
    assert 'href="#"' not in html


def test_dashboard_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    program = ProgramFactory.create(renewal_min_gwa_percent=Decimal("80"))
    user = _staff(program)
    AwardFactory.create_batch(50, source_application__program=program)
    for n in range(50):
        _waiting(program, n % 20)
    TaskFactory.create_batch(10, owner=user, program=program)
    client.force_login(user)
    with django_assert_max_num_queries(25):
        response = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug}))
    assert response.status_code == 200
