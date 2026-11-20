"""The staff dashboard's calendar (spec §12 rev 27): the user's own open tasks with a due date, the
program's distribution days (published or not; links to the schedule) and its application window."""

from datetime import date

from django.urls import reverse

from apps.accounts.models import User
from apps.core.calendar import CalendarEvent, MonthCalendar, grid_range, month_calendar
from apps.money.models import DistributionSchedule
from apps.programs.models import Program

from .models import Task


def staff_calendar(program: Program, user: User, *, today: date, month: date) -> MonthCalendar:
    """One month, Monday first. Two queries: tasks and distribution days in the grid."""
    start, end = grid_range(month)
    events: list[CalendarEvent] = []
    tasks = Task.objects.filter(
        owner=user, program=program, done_at__isnull=True, due_on__range=(start, end)
    ).only("pk", "title", "due_on")
    for task in tasks:
        assert task.due_on is not None
        url = reverse("workspace:task-edit", kwargs={"program": program.slug, "pk": task.pk})
        events.append(CalendarEvent(task.due_on, "task", task.title, "Task due", url))
    schedules = DistributionSchedule.objects.filter(
        program=program, distribution_date__range=(start, end)
    ).only("pk", "distribution_date", "claim_location", "is_published")
    for schedule in schedules:
        title = "Allowance release" if schedule.is_published else "Allowance release (draft)"
        url = reverse("money:schedule", kwargs={"program": program.slug, "schedule": schedule.pk})
        events.append(
            CalendarEvent(
                schedule.distribution_date, "release", title, schedule.claim_location, url
            )
        )
    if program.applications_open_on is not None:
        events.append(CalendarEvent(program.applications_open_on, "opens", "Applications open", ""))
    if program.applications_close_on is not None:
        events.append(
            CalendarEvent(program.applications_close_on, "closes", "Applications close", "Last day")
        )
    return month_calendar(month, today=today, events=events)
