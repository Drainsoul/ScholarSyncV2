"""The office overview: figures across programs, applications by month, what needs attention,
the programs table and recent activity (the approved mockup, minus what M11b and M11c bring)."""

from dataclasses import dataclass
from datetime import date, datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.review_selectors import (
    applications_by_month,
    submitted_counts,
    waiting_over,
)
from apps.awards.selectors import active_counts
from apps.core.activity import recent_activity, when
from apps.core.charts import MonthBar, first_month, month_bars
from apps.core.text import counted
from apps.money.selectors import budget_summary
from apps.programs.models import Program
from apps.programs.selectors import current_term, window_state
from apps.workspace.dashboard import WAIT_DAYS, day_month, waited_row

BUDGET_WARNING_PERCENT = 75


@dataclass(frozen=True)
class OfficeDashboard:
    greeting: str
    figures: list[dict[str, str]]
    months: list[MonthBar]
    attention: list[dict[str, str]]
    programs: list[dict[str, object]]
    activity: list[dict[str, str]]


def greeting(user: User, now: datetime) -> str:
    hour = timezone.localtime(now).hour
    part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    return f"Good {part}, {user.get_short_name()}"


def window_text(program: Program, today: date) -> str:
    state = window_state(program, today)
    if state == "closed":
        return "Applications closed"
    if state == "not_yet" and program.applications_open_on is not None:
        return f"Opens on {day_month(program.applications_open_on)}"
    if program.applications_close_on is not None:
        return f"Open until {day_month(program.applications_close_on)}"
    return "Open"


def office_dashboard(user: User, *, now: datetime) -> OfficeDashboard:
    today = timezone.localtime(now).date()
    programs = list(Program.objects.filter(is_active=True).order_by("name"))
    ids = [program.pk for program in programs]
    term = current_term()
    scholars = active_counts(ids)
    applied = (
        submitted_counts(ids, school_year_start=term.school_year_start) if term is not None else {}
    )
    waiting = waiting_over(ids, days=WAIT_DAYS, now=now)
    budgets = {program.pk: budget_summary(program, today.year) for program in programs}

    figures = [
        {"label": "Scholars", "value": f"{sum(scholars.values()):,}"},
        {"label": "Applications", "value": f"{sum(applied.values()):,}"},
        {
            "label": f"Waiting over {WAIT_DAYS} days",
            "value": f"{sum(count for count, _ in waiting.values()):,}",
        },
    ]

    attention: list[dict[str, str]] = []
    for program in programs:
        if program.pk in waiting:
            count, oldest = waiting[program.pk]
            words = counted(count, "application has", "applications have").split(" ", 1)
            attention.append(
                waited_row(
                    count,
                    oldest,
                    now,
                    f"{words[0]} {program.name} {words[1]} waited more than {WAIT_DAYS} days",
                    reverse("review:queue", kwargs={"program": program.slug}),
                )
            )
    for program in programs:
        used = budgets[program.pk].used_percent
        if used is not None and used >= BUDGET_WARNING_PERCENT:
            attention.append(
                {
                    "title": f"{program.name} has used {used}% of its budget",
                    "detail": f"Budget for {today.year}",
                    "tone": "warning",
                    "url": reverse("money:budget", kwargs={"program": program.slug}),
                }
            )

    rows: list[dict[str, object]] = [
        {
            "name": program.name,
            "url": reverse("workspace:dashboard", kwargs={"program": program.slug}),
            "window": window_text(program, today),
            "applications": applied.get(program.pk, 0),
            "scholars": scholars.get(program.pk, 0),
            "used_percent": budgets[program.pk].used_percent,
        }
        for program in programs
    ]
    activity = [
        {"what": sentence, "when": when(event.at), "datetime": event.at.isoformat()}
        for event, sentence in recent_activity()
    ]
    return OfficeDashboard(
        greeting=greeting(user, now),
        figures=figures,
        months=month_bars(applications_by_month(programs, since=first_month(today)), today=today),
        attention=attention,
        programs=rows,
        activity=activity,
    )
