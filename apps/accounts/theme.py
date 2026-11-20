"""Light, dark or the device's theme (spec §12 rev 29).

The choice lives in a cookie, not on the user: it belongs to the browser, works before sign-in and
costs no query. The server writes it into <html data-theme> and <meta name="color-scheme">, so the
page paints in the chosen theme straight away; the CSP rules out the usual inline script.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

PINNED = frozenset({"light", "dark"})
CHOICES = PINNED | {"system"}
ONE_YEAR = 365 * 24 * 60 * 60


def chosen_theme(request: HttpRequest) -> str:
    """'light' or 'dark' when pinned; '' to follow the device."""
    value = request.COOKIES.get(settings.THEME_COOKIE_NAME, "")
    return value if value in PINNED else ""


def theme(request: HttpRequest) -> dict[str, str]:
    """Context processor: the pinned theme, or '' for the device's."""
    return {"theme": chosen_theme(request)}


@require_POST
def set_theme(request: HttpRequest) -> HttpResponse:
    """Pin light or dark, or go back to the device's ("system"), then return to the page."""
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = "/"
    response = HttpResponseRedirect(target)
    choice = request.POST.get("theme", "")
    if choice in PINNED:
        response.set_cookie(
            settings.THEME_COOKIE_NAME,
            choice,
            max_age=ONE_YEAR,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=True,
            samesite="Lax",
        )
    elif choice == "system":
        response.delete_cookie(settings.THEME_COOKIE_NAME, samesite="Lax")
    return response
