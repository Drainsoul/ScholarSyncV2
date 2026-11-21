"""The calendar day dialog (spec §12 rev 33), shared by the student, staff and office calendars.

A day is a page of its own (`…/calendar/<YYYY-MM-DD>/`): the dialog body over HTMX, a full page in
the role's layout without JavaScript. Each area's view picks the events with the same builder as its
grid; this module lists that day's and renders them."""

from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

from apps.core.calendar import CalendarEvent, events_on

# The link under an event that has one: a task opens its edit page, a release day its schedule.
LINK_WORDS = {"task": "Open task", "release": "Open release day"}


def day_response(
    request: HttpRequest,
    *,
    day: date,
    events: Iterable[CalendarEvent],
    legend: list[tuple[str, str]],
    layout: str,
    shell_context: Callable[[], dict[str, Any]],
    back_url: str,
    add_task_url: str = "",
) -> HttpResponse:
    """`legend` names each kind as the grid's key does; `add_task_url` (staff and office) adds
    "Add task for this day"; `shell_context` is only built for the full page."""
    kinds = dict(legend)
    context: dict[str, Any] = {
        "day": day,
        "rows": [
            {
                "event": event,
                "kind": kinds.get(event.kind, ""),
                "link": LINK_WORDS.get(event.kind, "Open"),
            }
            for event in events_on(day, events)
        ],
        "add_task_url": (
            f"{add_task_url}?due={day.isoformat()}&from=dashboard" if add_task_url else ""
        ),
        "back_url": back_url,
    }
    if getattr(request, "htmx", False):
        response = render(request, "calendar/day_dialog.html", context)
    else:
        response = render(
            request, "calendar/day.html", {**shell_context(), **context, "layout": layout}
        )
    patch_vary_headers(response, ("HX-Request",))
    return response
