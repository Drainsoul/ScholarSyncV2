"""The staff dashboard calendar (spec §12 rev 27)."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.calendar import CalendarEvent, MonthCalendar, events_on
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.calendar import staff_calendar, staff_events
from apps.workspace.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
NOVEMBER = date(2026, 11, 1)
QUERIES_DAY_PAGE = 13  # session, user, membership checks, the shell (+ support), the events
QUERIES_DAY_DIALOG = 6  # no shell


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
    html = client.get(url).content.decode()
    assert "November 2026" in html and "Your task due" in html
    day = reverse("workspace:calendar-day", kwargs={"program": program.slug, "day": TODAY})
    assert f'href="{day}" hx-get="{day}" hx-target="#app-dialog-body"' in html
    assert 'aria-label="17 November 2026, no items"' in html
    assert "?due=" not in html and "Add a task due" not in html
    swap = client.get(
        url + "?month=2026-12", headers={"HX-Request": "true", "HX-Target": "staff-calendar"}
    )
    body = swap.content.decode()
    assert "<html" not in body and "December 2026" in body and "Print the list" in body
    assert 'aria-label="17 December 2026, 1 item"' in body
    assert "Needs attention" not in body
    assert "HX-Target" in swap["Vary"]


# The day dialog (spec §12 rev 33).


def _day_url(program: Program, day: date | str) -> str:
    return reverse("workspace:calendar-day", kwargs={"program": program.slug, "day": day})


def test_day_page_lists_tasks_and_releases_in_full(client: Any, vite_build: Any) -> None:
    program = ProgramFactory.create(applications_close_on=date(2026, 11, 21))
    user = _staff(program)
    title = "Call the TCU registrar about the missing grade reports for second year"
    task = TaskFactory.create(owner=user, program=program, title=title, due_on=date(2026, 11, 21))
    schedule = ScheduleFactory.create(
        program=program, distribution_date=date(2026, 11, 21), claim_location="City Hall lobby"
    )
    client.force_login(user)
    url = _day_url(program, "2026-11-21")
    assert url == f"/staff/{program.slug}/calendar/2026-11-21/"
    html = client.get(url).content.decode()
    assert "<h1>Saturday, 21 November 2026</h1>" in html and 'class="sidebar' in html
    assert title in html and "Your task due" in html and "Applications close" in html
    assert "City Hall lobby" in html
    edit = reverse("workspace:task-edit", kwargs={"program": program.slug, "pk": task.pk})
    assert f'href="{edit}"' in html and "Open task" in html
    money = reverse("money:schedule", kwargs={"program": program.slug, "schedule": schedule.pk})
    assert f'href="{money}"' in html and "Open release day" in html
    new = reverse("workspace:task-new", kwargs={"program": program.slug})
    assert f'href="{new}?due=2026-11-21&amp;from=dashboard"' in html
    assert "Add task for this day" in html


def test_day_dialog_is_only_the_dialog_body(client: Any, vite_build: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    response = client.get(
        _day_url(program, "2026-11-22"),
        headers={"HX-Request": "true", "HX-Target": "app-dialog-body"},
    )
    html = response.content.decode()
    assert response.status_code == 200 and "HX-Request" in response["Vary"]
    assert "<html" not in html and "sidebar" not in html
    assert 'id="app-dialog-title">Sunday, 22 November 2026</h2>' in html
    assert "Nothing on this day." in html and "Add task for this day" in html


def test_day_page_agrees_with_the_grid() -> None:
    program = ProgramFactory.create(applications_open_on=date(2026, 10, 27))
    user = _staff(program)
    day = date(2026, 10, 27)  # the November grid starts on 26 October
    TaskFactory.create(owner=user, program=program, title="B", due_on=day)
    ScheduleFactory.create(program=program, distribution_date=day)
    shown = staff_calendar(program, user, today=TODAY, month=NOVEMBER)
    [cell] = [c for week in shown.weeks for c in week if c.day == day]
    assert len(cell.events) == 3
    assert cell.events == events_on(day, staff_events(program, user, day, day))
    assert cell.url == _day_url(program, day)


def test_day_page_only_shows_this_program_and_own_tasks(client: Any) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(owner=_staff(program), program=program, title="Not mine", due_on=TODAY)
    TaskFactory.create(owner=user, program=ProgramFactory.create(), title="Elsewhere", due_on=TODAY)
    ScheduleFactory.create(distribution_date=TODAY, claim_location="Another program's hall")
    client.force_login(user)
    html = client.get(_day_url(program, TODAY)).content.decode()
    assert "Not mine" not in html and "Elsewhere" not in html
    assert "Another program&#x27;s hall" not in html and "Nothing on this day." in html


@pytest.mark.parametrize("value", ["2026-02-30", "2101-01-01", "21-11-2026"])
def test_day_page_bad_date_is_404(client: Any, value: str) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    assert client.get(f"/staff/{program.slug}/calendar/{value}/").status_code == 404


def test_day_page_of_an_unknown_program_is_404(client: Any) -> None:
    client.force_login(_staff(ProgramFactory.create()))
    assert client.get("/staff/no-such-program/calendar/2026-11-21/").status_code == 404


def test_day_page_query_budget(
    client: Any, vite_build: Any, django_assert_max_num_queries: Any
) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create_batch(10, owner=user, program=program, due_on=TODAY)
    for _ in range(5):
        ScheduleFactory.create(program=program, distribution_date=TODAY)
    client.force_login(user)
    url = _day_url(program, TODAY)
    with django_assert_max_num_queries(QUERIES_DAY_PAGE):
        assert client.get(url).status_code == 200
    with django_assert_max_num_queries(QUERIES_DAY_DIALOG):
        assert client.get(url, headers={"HX-Request": "true"}).status_code == 200
