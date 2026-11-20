"""A month calendar grid shared by the student home and the staff dashboard (spec §12 rev 26/27).

Each screen picks its own events; this module lays them on a Monday-first month and handles the
`?month=YYYY-MM` navigation."""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

Kind = Literal["release", "opens", "closes", "task"]

WEEKDAYS = [
    ("Monday", "Mon"),
    ("Tuesday", "Tue"),
    ("Wednesday", "Wed"),
    ("Thursday", "Thu"),
    ("Friday", "Fri"),
    ("Saturday", "Sat"),
    ("Sunday", "Sun"),
]


@dataclass(frozen=True)
class CalendarEvent:
    day: date
    kind: Kind
    title: str
    detail: str
    url: str = ""  # a site-relative link (a task), or none


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
    upcoming: list[CalendarEvent] = field(default_factory=list)


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


def grid_range(month: date) -> tuple[date, date]:
    """The first and last day the grid shows (whole weeks, so a few days of the next months)."""
    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        month.year, month.month
    )
    return weeks[0][0], weeks[-1][-1]


def month_calendar(
    month: date,
    *,
    today: date,
    events: Iterable[CalendarEvent],
    upcoming: list[CalendarEvent] | None = None,
) -> MonthCalendar:
    """Lay `events` on the month's grid; events outside it are dropped. A day's events by title."""
    weeks_raw = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        month.year, month.month
    )
    start, end = weeks_raw[0][0], weeks_raw[-1][-1]
    by_day: dict[date, list[CalendarEvent]] = {}
    for event in events:
        if start <= event.day <= end:
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
    return MonthCalendar(
        month=month,
        weeks=weeks,
        previous=_month_key(_shift(month, -1)),
        following=_month_key(_shift(month, 1)),
        is_current_month=month == today.replace(day=1),
        upcoming=upcoming or [],
    )


def days_until(day: date, today: date) -> str:
    gap = (day - today) // timedelta(days=1)
    if gap == 0:
        return "Today"
    if gap == 1:
        return "Tomorrow"
    return f"In {gap} days"
