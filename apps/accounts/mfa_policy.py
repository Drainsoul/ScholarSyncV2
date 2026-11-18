"""Two-factor sign-in is required for program staff and the office (spec §10, M13; ASVS V6.3.3).

With MFA_REQUIRED_FOR_STAFF on, a staff or office account without an authenticator reaches only
the 2FA, reauthentication and sign-out pages until it sets one up. The answer is cached in the
session once an authenticator exists, so ordinary pages pay no query."""

from collections.abc import Callable

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "mfa_ok"
EXEMPT_PREFIXES = (
    "/accounts/2fa/",
    "/accounts/logout/",
    "/accounts/reauthenticate/",
    "/static/",
    "/healthz",
)


class RequireStaffMfaMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if settings.MFA_REQUIRED_FOR_STAFF and self._must_activate(request):
            url = reverse("mfa_activate_totp")
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = url
                return response
            return redirect(url)
        return self.get_response(request)

    def _must_activate(self, request: HttpRequest) -> bool:
        user = request.user
        if not (user.is_authenticated and (user.is_program_staff or user.is_super_admin)):
            return False
        if request.session.get(SESSION_KEY) or request.path.startswith(EXEMPT_PREFIXES):
            return False
        if Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
            request.session[SESSION_KEY] = True
            return False
        return True
