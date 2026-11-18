"""Idle and absolute session limits (spec §10, M13; ASVS V7.3.1, V7.3.2; WCAG 2.2.1).

A signed-in session ends after `SESSION_IDLE_MINUTES_*` without a request, and 12 hours
(`SESSION_COOKIE_AGE`) after sign-in whatever the activity. Pages carry the seconds left, and
every signed-in response repeats the idle seconds in `X-Session-Idle`, so `frontend/src/session.ts`
can warn first from the server's clock. "Stay signed in" posts to the keep-alive view; the
script's own check when its timer runs out (`GET /accounts/session/status/`) is not activity, so
an unattended tab can't keep itself signed in. Last activity is written at most once a minute."""

import time
from collections.abc import Callable
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe

LAST_SEEN = "last_seen"
SIGNED_IN_AT = "signed_in_at"
WRITE_EVERY_SECONDS = 60
IDLE_MESSAGE = "You were signed out after a period of inactivity."
ABSOLUTE_MESSAGE = "You were signed out after 12 hours. Sign in again."
IDLE_HEADER = "X-Session-Idle"
STATUS_PATH = "/accounts/session/status/"


def idle_limit_seconds(user: object) -> int:
    staff = getattr(user, "is_program_staff", False) or getattr(user, "is_super_admin", False)
    minutes = (
        settings.SESSION_IDLE_MINUTES_STAFF if staff else settings.SESSION_IDLE_MINUTES_STUDENT
    )
    return int(float(minutes) * 60)


def _sign_out(request: HttpRequest, message: str) -> HttpResponse:
    next_path = request.get_full_path() if request.method == "GET" else "/"
    logout(request)
    messages.info(request, message)
    url = f"{reverse('account_login')}?{urlencode({'next': next_path})}"
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


class SessionPolicyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)
        now = time.time()
        session = request.session
        signed_in = float(session.setdefault(SIGNED_IN_AT, now))
        last_seen = float(session.setdefault(LAST_SEEN, now))
        idle = idle_limit_seconds(user)
        if now - signed_in > settings.SESSION_COOKIE_AGE:
            return _sign_out(request, ABSOLUTE_MESSAGE)
        if now - last_seen > idle:
            return _sign_out(request, IDLE_MESSAGE)
        if now - last_seen >= WRITE_EVERY_SECONDS and request.path != STATUS_PATH:
            session[LAST_SEEN] = now
            last_seen = now
        request.session_policy = {  # type: ignore[attr-defined]
            "idle": max(0, int(idle - (now - last_seen))),
            "absolute": max(0, int(settings.SESSION_COOKIE_AGE - (now - signed_in))),
        }
        response = self.get_response(request)
        if request.user.is_authenticated and LAST_SEEN in request.session:
            # Read again: the view may have recorded activity (keep-alive).
            left = idle - (time.time() - float(request.session[LAST_SEEN]))
            response[IDLE_HEADER] = str(max(0, int(left)))
        return response


@login_required
@require_safe
def status(request: HttpRequest) -> JsonResponse:
    """The seconds left, for the warning script; reading it doesn't count as activity."""
    return JsonResponse(request.session_policy)  # type: ignore[attr-defined]


@login_required
@require_POST
def keep_alive(request: HttpRequest) -> HttpResponse:
    """ "Stay signed in": counts as activity now."""
    request.session[LAST_SEEN] = time.time()
    return HttpResponse(status=204)
