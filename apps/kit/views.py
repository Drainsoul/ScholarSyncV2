"""Design kit (spec §12): every component in every state, and the key-screen mockups.

Development only: every view answers 404 unless settings.KIT_ENABLED, and pages are never indexed.
"""

import json
from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from apps.kit.forms import KitForm, invalid_kit_form

View = Callable[..., HttpResponse]

ICONS_DIR = settings.BASE_DIR / "frontend" / "src" / "icons"

# (section id, title); the index includes kit/sections/<id>.html for each, in order.
SECTIONS: list[tuple[str, str]] = [
    ("colour", "Colour"),
    ("type", "Type"),
    ("icons", "Icons"),
    ("controls", "Controls"),
]

SWATCHES = [
    "brand-700", "brand-600", "brand-500", "brand-400", "brand-50", "accent", "accent-50",
    "navy-800", "navy-700", "navy-muted", "info", "info-50", "success", "success-50",
    "warning", "warning-50", "gray-900", "gray-800", "gray-700", "gray-600", "gray-500",
    "gray-400", "gray-300", "gray-200", "gray-100", "gray-50", "white",
]  # fmt: skip


def kit_only(view: View) -> View:
    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not settings.KIT_ENABLED:
            raise Http404
        response = view(request, *args, **kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    return wrapper


def icon_names() -> list[str]:
    names: list[str] = json.loads((ICONS_DIR / "icons.json").read_text(encoding="utf-8"))
    return names + sorted(path.stem for path in ICONS_DIR.glob("*.svg"))


def index_context(request: HttpRequest) -> dict[str, object]:
    return {
        "sections": [
            {"id": key, "title": title, "template": f"kit/sections/{key}.html"}
            for key, title in SECTIONS
        ],
        "swatches": SWATCHES,
        "icons": icon_names(),
        "empty_form": KitForm(prefix="empty"),
        "invalid_form": invalid_kit_form(),
    }


@kit_only
@require_safe
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "kit/index.html", index_context(request))
