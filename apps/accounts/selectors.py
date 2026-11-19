"""Reads for accounts: the office's list of staff and office accounts, and a user's sessions."""

from dataclasses import dataclass
from datetime import datetime

from allauth.usersessions.models import UserSession
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.db.models import Prefetch, Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.programs.models import ProgramMembership

from .models import User


def staff_accounts(q: str = "") -> QuerySet[User]:
    """Staff and office accounts (never students), by name, with their memberships."""
    rows = User.objects.filter(role__in=[User.Role.STAFF, User.Role.SUPER_ADMIN])
    for word in q.split():
        rows = rows.filter(Q(full_name__icontains=word) | Q(email__icontains=word))
    return rows.order_by("full_name", "email").prefetch_related(
        Prefetch(
            "memberships",
            queryset=ProgramMembership.objects.select_related("program").order_by("program__name"),
        )
    )


def staff_account(pk: int) -> User | None:
    return staff_accounts().filter(pk=pk).first()


@dataclass(frozen=True)
class LiveSession:
    signed_in_at: datetime | None
    ip: str
    user_agent: str
    is_current: bool
    recorded: bool


def _newest_first(session: LiveSession) -> tuple[bool, float]:
    stamp = session.signed_in_at.timestamp() if session.signed_in_at else 0.0
    return (not session.is_current, -stamp)


def live_sessions(user: User, request: HttpRequest) -> list[LiveSession]:
    """Every unexpired session signed in as `user`, read from the session table (the truth, as
    `services._end_sessions` uses), with allauth's browser and address where it recorded them.
    A session allauth lost track of still shows, so none is hidden from "Sign out other sessions".
    The current browser comes first."""
    current = request.session.session_key
    recorded = {row.session_key: row for row in UserSession.objects.filter(user=user)}
    found: list[LiveSession] = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        data = session.get_decoded()
        if data.get(SESSION_KEY) != str(user.pk):
            continue
        row = recorded.get(session.session_key)
        is_current = session.session_key == current
        signed_in_at = row.created_at if row is not None else None
        if signed_in_at is None and isinstance(data.get("signed_in_at"), int | float):
            zone = timezone.get_current_timezone()
            signed_in_at = datetime.fromtimestamp(data["signed_in_at"], tz=zone)
        if row is not None:
            ip, agent = row.ip, row.user_agent
        elif is_current:
            ip, agent = "", request.META.get("HTTP_USER_AGENT", "")
        else:
            ip, agent = "", ""
        known = row is not None or is_current
        found.append(LiveSession(signed_in_at, ip, agent, is_current, known))
    found.sort(key=_newest_first)
    return found
