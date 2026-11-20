"""The staff dashboard calendar (spec §12 rev 27)."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.calendar import CalendarEvent, MonthCalendar
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.calendar import staff_calendar
from apps.workspace.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
NOVEMBER = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


def _staff(program: Program) -> User:
    return MembershipFactory.create(program=program).user


def _events(shown: MonthCalendar) -> dict[date, list[CalendarEvent]]:
    return {cell.day: list(cell.events) for week in shown.weeks for cell in week if cell.events}


def test_own_open_dated_tasks_link_to_the_task() -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    mine = TaskFactory.create(
        owner=user, program=program, title="Call TCU", due_on=date(2026, 11, 20)
    )
    TaskFactory.create(owner=user, program=program, title="Undated", due_on=None)
    TaskFactory.create(owner=user, program=program, title="Done", due_on=TODAY, done_at=NOW)
    TaskFactory.create(owner=_staff(program), program=program, title="Someone else's", due_on=TODAY)
    TaskFactory.create(
        owner=user, program=ProgramFactory.create(), title="Other program", due_on=TODAY
    )
    events = _events(staff_calendar(program, user, today=TODAY, month=NOVEMBER))
    assert list(events) == [date(2026, 11, 20)]
    [task] = events[date(2026, 11, 20)]
    assert (task.kind, task.title) == ("task", "Call TCU")
    assert task.url == reverse(
        "workspace:task-edit", kwargs={"program": program.slug, "pk": mine.pk}
    )


def test_release_days_published_or_draft_and_the_window() -> None:
    program = ProgramFactory.create(
        applications_open_on=date(2026, 11, 3), applications_close_on=date(2026, 11, 28)
    )
    ScheduleFactory.create(program=program, distribution_date=date(2026, 11, 10), is_published=True)
    ScheduleFactory.create(
        program=program, distribution_date=date(2026, 11, 12), is_published=False
    )
    ScheduleFactory.create(distribution_date=date(2026, 11, 14))  # another program
    events = _events(staff_calendar(program, _staff(program), today=TODAY, month=NOVEMBER))
    titles = {day.day: [(e.kind, e.title) for e in found] for day, found in events.items()}
    assert titles == {
        3: [("opens", "Applications open")],
        10: [("release", "Allowance release")],
        12: [("release", "Allowance release (draft)")],
        28: [("closes", "Applications close")],
    }
    assert events[date(2026, 11, 10)][0].url.endswith(
        "/disbursements/"
        + str(program.schedules.get(distribution_date=date(2026, 11, 10)).pk)
        + "/"
    )


def test_month_is_whole_weeks_monday_first_and_marks_today() -> None:
    program = ProgramFactory.create()
    shown = staff_calendar(program, _staff(program), today=TODAY, month=NOVEMBER)
    assert shown.weeks[0][0].day == date(2026, 10, 26)  # a Monday
    assert [cell.day for week in shown.weeks for cell in week if cell.is_today] == [TODAY]
    assert (shown.previous, shown.following, shown.is_current_month) == ("2026-10", "2026-12", True)


def test_dashboard_calendar_page_and_month_swap(client: Any) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(
        owner=user, program=program, title="Print the list", due_on=TODAY + timedelta(30)
    )
    client.force_login(user)
    url = reverse("workspace:dashboard", kwargs={"program": program.slug})
    new = reverse("workspace:task-new", kwargs={"program": program.slug})
    html = client.get(url).content.decode()
    assert "November 2026" in html and "Your task due" in html
    assert f'href="{new}?due=2026-11-17&amp;from=dashboard"' in html
    assert 'aria-label="Add a task due 17 November 2026"' in html
    swap = client.get(
        url + "?month=2026-12", headers={"HX-Request": "true", "HX-Target": "staff-calendar"}
    )
    body = swap.content.decode()
    assert "<html" not in body and "December 2026" in body and "Print the list" in body
    assert "Needs attention" not in body
    assert "HX-Target" in swap["Vary"]
