"""Public information pages (open-source spec section 15): about, privacy, terms and so on.

The text is template text. Whoever hosts a copy edits the templates to fit their organisation
and law.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

REPO_URL = "https://github.com/Drainsoul/ScholarSyncV2"


def _duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{seconds} seconds"


def _context() -> dict[str, object]:
    return {
        "operator_name": settings.SITE_OPERATOR_NAME,
        "contact_email": settings.PRIVACY_CONTACT_EMAIL,
        "notice_version": settings.PRIVACY_NOTICE_VERSION,
        "explore": settings.EXPLORE,
        "repo_url": REPO_URL,
    }


@require_safe
def about(request: HttpRequest) -> HttpResponse:
    return render(request, "core/pages/about.html", _context())


@require_safe
def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "core/pages/privacy.html", _context())


@require_safe
def terms(request: HttpRequest) -> HttpResponse:
    return render(request, "core/pages/terms.html", _context())


@require_safe
def cookies(request: HttpRequest) -> HttpResponse:
    context = _context() | {
        "cookies": [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "purpose": "Keeps you signed in.",
                "lifetime": (
                    f"Up to {_duration(settings.SESSION_COOKIE_AGE)}, then you sign in again."
                ),
            },
            {
                "name": settings.CSRF_COOKIE_NAME,
                "purpose": "Protects forms from being submitted by other sites.",
                "lifetime": f"Up to {_duration(settings.CSRF_COOKIE_AGE)}.",
            },
        ]
    }
    return render(request, "core/pages/cookies.html", context)


@require_safe
def help_page(request: HttpRequest) -> HttpResponse:
    return render(request, "core/pages/help.html", _context())


@require_safe
def contact(request: HttpRequest) -> HttpResponse:
    return render(request, "core/pages/contact.html", _context())
