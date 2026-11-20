"""The student home's calendar (spec §12 rev 26): release days of the programs the student holds and
the application windows of programs they qualify for or have an unfinished application in."""

from datetime import date

from django.db.models import Exists, OuterRef

from apps.accounts.models import User
from apps.awards.models import Award, ScholarTerm
from apps.core.calendar import (
    CalendarEvent,
    MonthCalendar,
    days_until,
    grid_range,
    month_calendar,
    parse_month,
)
from apps.matching.eligibility import CheckState
from apps.matching.selectors import MatchPage
from apps.money.models import DistributionSchedule
from apps.programs.models import Program

__all__ = ["MonthCalendar", "days_until", "parse_month", "student_calendar"]

UPCOMING_SHOWN = 5
HELD_FOR_RELEASES = (Award.Status.ACTIVE, Award.Status.SUSPENDED)


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
    start, end = grid_range(month)
    windows = _window_events(_window_programs(page))
    # As the award card's "Next release": only terms the student is a scholar in.
    scholar_in = ScholarTerm.objects.filter(
        award__profile__user=user,
        award__status__in=HELD_FOR_RELEASES,
        award__program_id=OuterRef("program_id"),
        term_id=OuterRef("term_id"),
    )
    schedules = DistributionSchedule.objects.filter(
        Exists(scholar_in), is_published=True
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
    upcoming = sorted(
        [*coming, *(e for e in windows if e.day >= today)], key=lambda e: (e.day, e.title)
    )[:UPCOMING_SHOWN]
    return month_calendar(month, today=today, events=[*in_grid, *windows], upcoming=upcoming)
