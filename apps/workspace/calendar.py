"""Dashboard calendars (spec §12 rev 27).

Staff: the user's own open tasks in the program, its distribution days (published or not; links to
the schedule) and its application window. Office: the user's own office tasks, and the same dates
for every active program, each named with its program."""

from collections.abc import Callable, Iterable
from datetime import date

from django.urls import reverse

from apps.accounts.models import User
from apps.core.calendar import CalendarEvent, MonthCalendar, grid_range, month_calendar
from apps.money.models import DistributionSchedule
from apps.programs.models import Program

from .models import Task


def _task_events(
    user: User, program: Program | None, start: date, end: date, edit_url: Callable[[int], str]
) -> list[CalendarEvent]:
    """The owner's open tasks due in the grid; `program` None is the office's own."""
    tasks = Task.objects.filter(
        owner=user, program=program, done_at__isnull=True, due_on__range=(start, end)
    ).only("pk", "title", "due_on")
    events = []
    for task in tasks:
        assert task.due_on is not None
        events.append(CalendarEvent(task.due_on, "task", task.title, "Task due", edit_url(task.pk)))
    return events


def _program_events(
    programs: Iterable[Program], start: date, end: date, *, named: bool
) -> list[CalendarEvent]:
    """Distribution days and application window dates from `start` to `end`. One query."""
    by_id = {program.pk: program for program in programs}

    def prefix(program: Program) -> str:
        return f"{program.name} " if named else ""

    events = []
    schedules = DistributionSchedule.objects.filter(
        program_id__in=by_id, distribution_date__range=(start, end)
    ).only("pk", "program_id", "distribution_date", "claim_location", "is_published")
    for schedule in schedules:
        program = by_id[schedule.program_id]
        release = "allowance release" if named else "Allowance release"
        title = prefix(program) + release + ("" if schedule.is_published else " (draft)")
        url = reverse("money:schedule", kwargs={"program": program.slug, "schedule": schedule.pk})
        events.append(
            CalendarEvent(
                schedule.distribution_date, "release", title, schedule.claim_location, url
            )
        )
    for program in by_id.values():
        opens = "applications open" if named else "Applications open"
        closes = "applications close" if named else "Applications close"
        if program.applications_open_on is not None:
            events.append(
                CalendarEvent(program.applications_open_on, "opens", prefix(program) + opens, "")
            )
        if program.applications_close_on is not None:
            events.append(
                CalendarEvent(
                    program.applications_close_on, "closes", prefix(program) + closes, "Last day"
                )
            )
    return [event for event in events if start <= event.day <= end]


def staff_events(program: Program, user: User, start: date, end: date) -> list[CalendarEvent]:
    """The staff member's events from `start` to `end` (the grid, or one day). Two queries."""

    def edit_url(pk: int) -> str:
        return reverse("workspace:task-edit", kwargs={"program": program.slug, "pk": pk})

    return [
        *_task_events(user, program, start, end, edit_url),
        *_program_events([program], start, end, named=False),
    ]


def staff_calendar(program: Program, user: User, *, today: date, month: date) -> MonthCalendar:
    """One month, Monday first. Two queries: tasks and distribution days in the grid."""
    start, end = grid_range(month)

    def day_url(day: date) -> str:
        return reverse("workspace:calendar-day", kwargs={"program": program.slug, "day": day})

    events = staff_events(program, user, start, end)
    return month_calendar(month, today=today, events=events, day_url=day_url)


def office_events(user: User, start: date, end: date) -> list[CalendarEvent]:
    """The office user's events from `start` to `end` (the grid, or one day). Three queries:
    tasks, active programs, distribution days."""

    def edit_url(pk: int) -> str:
        return reverse("office:task-edit", kwargs={"pk": pk})

    programs = Program.objects.filter(is_active=True).order_by("name")
    return [
        *_task_events(user, None, start, end, edit_url),
        *_program_events(programs, start, end, named=True),
    ]


def office_calendar(user: User, *, today: date, month: date) -> MonthCalendar:
    """One month, Monday first. Three queries: tasks, active programs, distribution days."""
    start, end = grid_range(month)

    def day_url(day: date) -> str:
        return reverse("office:calendar-day", kwargs={"day": day})

    events = office_events(user, start, end)
    return month_calendar(month, today=today, events=events, day_url=day_url)
