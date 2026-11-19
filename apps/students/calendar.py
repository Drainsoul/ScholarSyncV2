"""The student home's calendar (spec §12 rev 26): release days of the programs the student holds and
the application windows of programs they qualify for or have an unfinished application in."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from apps.accounts.models import User
from apps.awards.models import Award
from apps.matching.eligibility import CheckState
from apps.matching.selectors import MatchPage
from apps.money.models import DistributionSchedule
from apps.programs.models import Program

UPCOMING_SHOWN = 5
HELD_FOR_RELEASES = (Award.Status.ACTIVE, Award.Status.SUSPENDED)
Kind = Literal["release", "opens", "closes"]


@dataclass(frozen=True)
class CalendarEvent:
    day: date
    kind: Kind
    title: str
    detail: str


@dataclass(frozen=True)
class CalendarDay:
    day: date
    in_month: bool
    is_today: bool
    events: tuple[CalendarEvent, ...]


@dataclass(frozen=True)
class MonthCalendar:
    month: date  # the first of the month shown
    weeks: list[list[CalendarDay]]
    previous: str  # YYYY-MM
    following: str
    is_current_month: bool
    upcoming: list[CalendarEvent]


def parse_month(value: str | None, *, today: date) -> date:
    """`YYYY-MM` from the query string; anything else (or a year out of range) is this month."""
    this_month = today.replace(day=1)
    if not value or len(value) != 7 or value[4] != "-":
        return this_month
    year, month = value[:4], value[5:]
    if not (year.isdigit() and month.isdigit()):
        return this_month
    if not (2000 <= int(year) <= 2100 and 1 <= int(month) <= 12):
        return this_month
    return date(int(year), int(month), 1)


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _shift(month: date, by: int) -> date:
    index = month.year * 12 + month.month - 1 + by
    return date(index // 12, index % 12 + 1, 1)


def _window_programs(page: MatchPage) -> list[Program]:
    """Programs whose window dates matter to this student: they pass every rule but the window
    (so a window that hasn't opened yet still shows), or they have an unfinished application."""
    found = []
    for match in page.matches:
        if match.held or match.rejected:
            continue
        others_met = all(
            check.state == CheckState.MET for check in match.result.checks if check.code != "window"
        )
        if match.open_application_id is not None or others_met:
            found.append(match.program)
    return found


def _window_events(programs: list[Program]) -> list[CalendarEvent]:
    events = []
    for program in programs:
        if program.applications_open_on is not None:
            events.append(
                CalendarEvent(
                    program.applications_open_on,
                    "opens",
                    f"{program.name} applications open",
                    "",
                )
            )
        if program.applications_close_on is not None:
            events.append(
                CalendarEvent(
                    program.applications_close_on,
                    "closes",
                    f"{program.name} applications close",
                    "Last day to submit",
                )
            )
    return events


def _release_event(schedule: DistributionSchedule) -> CalendarEvent:
    return CalendarEvent(
        schedule.distribution_date,
        "release",
        f"{schedule.program.name} allowance release",
        schedule.claim_location,
    )


def student_calendar(user: User, page: MatchPage, *, today: date, month: date) -> MonthCalendar:
    """One month, Monday first, plus the next dates from today. Two queries for release days."""
    weeks_raw = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        month.year, month.month
    )
    start, end = weeks_raw[0][0], weeks_raw[-1][-1]
    windows = _window_events(_window_programs(page))
    held = Award.objects.filter(profile__user=user, status__in=HELD_FOR_RELEASES).values(
        "program_id"
    )
    schedules = DistributionSchedule.objects.filter(
        is_published=True, program_id__in=held
    ).select_related("program")
    in_grid = [
        _release_event(schedule)
        for schedule in schedules.filter(distribution_date__range=(start, end))
    ]
    coming = [
        _release_event(schedule)
        for schedule in schedules.filter(distribution_date__gte=today).order_by(
            "distribution_date", "pk"
        )[:UPCOMING_SHOWN]
    ]
    by_day: dict[date, list[CalendarEvent]] = {}
    for event in [*in_grid, *(e for e in windows if start <= e.day <= end)]:
        by_day.setdefault(event.day, []).append(event)
    weeks = [
        [
            CalendarDay(
                day,
                day.month == month.month,
                day == today,
                tuple(sorted(by_day.get(day, []), key=lambda e: e.title)),
            )
            for day in week
        ]
        for week in weeks_raw
    ]
    upcoming = sorted(
        [*coming, *(e for e in windows if e.day >= today)], key=lambda e: (e.day, e.title)
    )[:UPCOMING_SHOWN]
    return MonthCalendar(
        month=month,
        weeks=weeks,
        previous=_month_key(_shift(month, -1)),
        following=_month_key(_shift(month, 1)),
        is_current_month=month == today.replace(day=1),
        upcoming=upcoming,
    )


def days_until(day: date, today: date) -> str:
    gap = (day - today) // timedelta(days=1)
    if gap == 0:
        return "Today"
    if gap == 1:
        return "Tomorrow"
    return f"In {gap} days"
