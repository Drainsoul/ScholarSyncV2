"""The staff dashboard: figures, what needs attention, applications by month and own tasks."""

from dataclasses import dataclass
from datetime import date, datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.review_selectors import (
    WAITING_STATUSES,
    applications_by_month,
    waiting_over,
)
from apps.awards.models import Award
from apps.awards.selectors import at_risk_q, with_latest_term
from apps.core.charts import MonthBar, first_month, month_bars
from apps.core.templatetags.ui import peso
from apps.core.text import counted
from apps.money.selectors import payout_counts, released_in_year
from apps.programs.models import Program
from apps.programs.selectors import current_term, window_state

from .models import Task
from .tasks import open_tasks

WAIT_DAYS = 7
CLOSING_SOON_DAYS = 14
TASKS_SHOWN = 5


@dataclass(frozen=True)
class StaffDashboard:
    figures: list[dict[str, str]]
    attention: list[dict[str, str]]
    months: list[MonthBar]
    tasks: list[Task]
    term_label: str


def day_month(day: date) -> str:
    """ "3 November": the day without a leading zero, then the month."""
    return f"{day.day} {day:%B}"


def in_days(days: int, word: str) -> str:
    return f"{word} in {counted(days, 'day', 'days')}"


def window_row(program: Program, today: date) -> dict[str, str] | None:
    """An attention row when the window opens later, or closes within two weeks."""
    url = reverse("programs:detail", kwargs={"slug": program.slug})
    state = window_state(program, today)
    if state == "not_yet" and program.applications_open_on is not None:
        opens = program.applications_open_on
        return {
            "title": f"Applications open on {day_month(opens)}",
            "detail": in_days((opens - today).days, "Starts"),
            "tone": "info",
            "url": url,
        }
    closes = program.applications_close_on
    if state == "open" and closes is not None and (closes - today).days <= CLOSING_SOON_DAYS:
        return {
            "title": f"Applications close on {day_month(closes)}",
            "detail": in_days((closes - today).days, "Ends"),
            "tone": "warning",
            "url": url,
        }
    return None


def waited_row(
    count: int, oldest: datetime | None, now: datetime, title: str, url: str
) -> dict[str, str]:
    detail = ""
    if oldest is not None:
        detail = f"Oldest sent {counted((now - oldest).days, 'day', 'days')} ago"
    return {"title": title, "detail": detail, "tone": "danger", "url": url}


def staff_dashboard(program: Program, user: User, *, now: datetime) -> StaffDashboard:
    today = timezone.localtime(now).date()
    term = current_term()
    slug = {"program": program.slug}
    awards = Award.objects.filter(program=program)
    active = awards.filter(status=Award.Status.ACTIVE).count()
    at_risk = with_latest_term(awards).filter(at_risk_q(program, term, today)).count()
    waiting = Application.objects.filter(program=program, status__in=WAITING_STATUSES).count()
    figures = [
        {"label": "Active scholars", "value": f"{active:,}"},
        {"label": "Applications waiting", "value": f"{waiting:,}"},
        {"label": "Released this year", "value": peso(released_in_year(program, today.year))},
        {"label": "At risk", "value": f"{at_risk:,}"},
    ]

    attention: list[dict[str, str]] = []
    count, oldest = waiting_over([program.pk], days=WAIT_DAYS, now=now).get(program.pk, (0, None))
    if count:
        title = counted(count, "application has", "applications have")
        attention.append(
            waited_row(
                count,
                oldest,
                now,
                f"{title} waited more than {WAIT_DAYS} days",
                reverse("review:queue", kwargs=slug),
            )
        )
    tasks = open_tasks(user, program, today=today)
    overdue = tasks.filter(due_on__lt=today).count()
    if overdue:
        attention.append(
            {
                "title": f"{overdue} of your tasks {'is' if overdue == 1 else 'are'} overdue",
                "detail": "Open your task list",
                "tone": "danger",
                "url": reverse("workspace:tasks", kwargs=slug),
            }
        )
    if at_risk:
        attention.append(
            {
                "title": f"{counted(at_risk, 'scholar is', 'scholars are')} at risk",
                "detail": "Check their grades and renewals",
                "tone": "warning",
                "url": reverse("scholars:list", kwargs=slug) + "?status=at_risk",
            }
        )
    payouts = payout_counts(program)
    money_url = reverse("money:overview", kwargs=slug)
    if payouts["pending"]:
        title = counted(payouts["pending"], "payout is", "payouts are")
        attention.append(
            {
                "title": f"{title} prepared and waiting for a head",
                "detail": "A head approves them in Disbursements",
                "tone": "warning",
                "url": money_url,
            }
        )
    if payouts["approved"]:
        one = payouts["approved"] == 1
        title = counted(payouts["approved"], "approved payout is", "approved payouts are")
        attention.append(
            {
                "title": f"{title} ready to release",
                "detail": f"Release {'it' if one else 'them'} on or after the distribution day",
                "tone": "info",
                "url": money_url,
            }
        )
    window = window_row(program, today)
    if window is not None:
        attention.append(window)

    start = first_month(today)
    return StaffDashboard(
        figures=figures,
        attention=attention,
        months=month_bars(applications_by_month([program], since=start), today=today),
        tasks=list(tasks[:TASKS_SHOWN]),
        term_label=str(term) if term is not None else "",
    )
