"""Reads for the audit log (spec §12, M11c): filters, the scoped event list and details."""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Q, QuerySet
from django.http import QueryDict
from django.utils import timezone

from apps.programs.models import Program

from .activity import AUDIT_GROUPS
from .models import AuditEvent
from .params import positive_id


@dataclass(frozen=True)
class AuditFilters:
    group: str = ""
    start: date | None = None
    end: date | None = None
    who: int | None = None
    program: str = ""  # "" all, "none", or a program id (the office only)


# Dates outside these years fall back to "all": a day past 9999-12-31 would overflow.
FIRST_YEAR, LAST_YEAR = 1900, 9998


def _date(raw: str) -> date | None:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if FIRST_YEAR <= parsed.year <= LAST_YEAR else None


def parse_audit_filters(params: QueryDict, *, office: bool) -> AuditFilters:
    """Bad values fall back to "all", never an error. Heads never filter by program."""
    group = params.get("group", "")
    if group not in AUDIT_GROUPS:
        group = ""
    program = ""
    if office:
        raw = params.get("program", "")
        if raw == "none":
            program = "none"
        else:
            program_id = positive_id(raw)
            if program_id is not None and Program.objects.filter(pk=program_id).exists():
                program = str(program_id)
    return AuditFilters(
        group=group,
        start=_date(params.get("start", "")),
        end=_date(params.get("end", "")),
        who=positive_id(params.get("who", "")),
        program=program,
    )


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.get_default_timezone())


def audit_events(filters: AuditFilters, *, program: Program | None) -> QuerySet[AuditEvent]:
    """Events newest first. A given `program` (a head's page) always wins over the filters."""
    rows = AuditEvent.objects.select_related("actor", "program")
    if program is not None:
        rows = rows.filter(program=program)
    elif filters.program == "none":
        rows = rows.filter(program__isnull=True)
    elif filters.program:
        rows = rows.filter(program_id=int(filters.program))
    if filters.group:
        prefixes = AUDIT_GROUPS[filters.group][1]
        match = Q()
        for prefix in prefixes:
            match |= Q(action__startswith=f"{prefix}.")
        rows = rows.filter(match)
    if filters.start is not None:
        rows = rows.filter(at__gte=_day_start(filters.start))
    if filters.end is not None:
        rows = rows.filter(at__lt=_day_start(filters.end + timedelta(days=1)))
    if filters.who is not None:
        rows = rows.filter(actor_id=filters.who)
    return rows.order_by("-at", "-pk")


def details(event: AuditEvent) -> list[tuple[str, str]]:
    """The event's data as "key: value" pairs; lists and dicts as JSON."""
    data = event.data if isinstance(event.data, dict) else {}
    return [
        (str(key), json.dumps(value) if isinstance(value, list | dict) else str(value))
        for key, value in data.items()
    ]
