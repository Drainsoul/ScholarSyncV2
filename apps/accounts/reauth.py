"""Reauthentication that rotates the session key, and the session list behind it (spec §10, M13;
ASVS V7.2.4, V7.4.5, V7.5.2)."""

from typing import Any

from allauth.account.decorators import reauthentication_required
from allauth.account.views import ReauthenticateView as AllauthReauthenticateView
from allauth.usersessions.models import UserSession
from allauth.usersessions.views import ListUserSessionsView
from django.http import HttpResponse
from django.utils.decorators import method_decorator


class ReauthenticateView(AllauthReauthenticateView):  # type: ignore[misc]
    """allauth's password confirmation, mounted at the same path; a fresh session key afterwards
    means a key seen before the sensitive step can't ride along after it."""

    def form_valid(self, form: Any) -> HttpResponse:
        response: HttpResponse = super().form_valid(form)
        session = self.request.session
        old_key = session.session_key
        session.cycle_key()
        # Keep the session list's row on the rotated key, or it would vanish from the list.
        if old_key:
            UserSession.objects.filter(session_key=old_key).update(session_key=session.session_key)
        return response


@method_decorator(reauthentication_required, name="post")
class SessionListView(ListUserSessionsView):  # type: ignore[misc]
    """allauth's session list; signing the other sessions out asks for the password again."""
