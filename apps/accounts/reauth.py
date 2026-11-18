"""Reauthentication that rotates the session key, and the session list behind it (spec §10, M13;
ASVS V7.2.4, V7.4.5, V7.5.2)."""

from typing import Any

from allauth.account.decorators import reauthentication_required
from allauth.account.views import ReauthenticateView as AllauthReauthenticateView
from allauth.mfa.base.views import ReauthenticateView as AllauthMfaReauthenticateView
from allauth.usersessions.models import UserSession
from allauth.usersessions.views import ListUserSessionsView
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator

from .services import end_other_sessions


def rotate_session_key(request: HttpRequest) -> None:
    """A fresh session key after a sensitive confirmation, so a key seen before it can't ride
    along after it. The session list's row moves to the new key, or it would vanish."""
    session = request.session
    old_key = session.session_key
    session.cycle_key()
    if old_key:
        UserSession.objects.filter(session_key=old_key).update(session_key=session.session_key)


class ReauthenticateView(AllauthReauthenticateView):  # type: ignore[misc]
    """allauth's password confirmation, mounted at the same path, plus a new session key."""

    def form_valid(self, form: Any) -> HttpResponse:
        response: HttpResponse = super().form_valid(form)
        rotate_session_key(self.request)
        return response


class MfaReauthenticateView(AllauthMfaReauthenticateView):  # type: ignore[misc]
    """allauth's authenticator-code confirmation, mounted at the same path, plus a new key."""

    def form_valid(self, form: Any) -> HttpResponse:
        response: HttpResponse = super().form_valid(form)
        rotate_session_key(self.request)
        return response


@method_decorator(reauthentication_required, name="post")
class SessionListView(ListUserSessionsView):  # type: ignore[misc]
    """allauth's session list; signing the other sessions out asks for the password again and
    is audited through the accounts service."""

    def form_valid(self, form: Any) -> HttpResponse:
        ended = end_other_sessions(user=self.request.user, request=self.request)
        messages.success(
            self.request, f"Signed out of {ended} other session{'s' if ended != 1 else ''}."
        )
        # FormView's redirect, skipping allauth's own save (it would end the sessions unaudited).
        response: HttpResponse = super(ListUserSessionsView, self).form_valid(form)
        return response
