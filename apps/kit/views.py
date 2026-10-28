"""Design kit (spec §12): every component in every state, and the key-screen mockups.

Development only: every view answers 404 unless settings.KIT_ENABLED, and pages are never indexed.
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_safe

from apps.kit import samples
from apps.kit.forms import KitForm, invalid_kit_form

View = Callable[..., HttpResponse]

ICONS_DIR = settings.BASE_DIR / "frontend" / "src" / "icons"

# (section id, title); the index includes kit/sections/<id>.html for each, in order.
SECTIONS: list[tuple[str, str]] = [
    ("colour", "Colour"),
    ("type", "Type"),
    ("icons", "Icons"),
    ("controls", "Controls"),
    ("data", "Data display"),
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


SORTS: dict[str, Callable[[samples.Scholar], Any]] = {
    "name": lambda row: row["name"],
    "school": lambda row: row["school"],
    "amount": lambda row: row["amount"],
}


def filtered_scholars(params: QueryDict) -> list[samples.Scholar]:
    """Filter and sort the sample rows. Unknown statuses and sort keys are ignored, never errors."""
    rows = samples.scholars()
    query = params.get("q", "").strip().casefold()
    if query:
        rows = [row for row in rows if query in row["name"].casefold()]
    status = params.get("status", "")
    if status in samples.STATUSES:
        rows = [row for row in rows if row["status"] == status]
    sort = params.get("sort", "name")
    if key := SORTS.get(sort.removeprefix("-")):
        rows.sort(key=key, reverse=sort.startswith("-"))
    return rows


def index_context(request: HttpRequest) -> dict[str, object]:
    rows = filtered_scholars(request.GET)
    return {
        "sections": [
            {"id": key, "title": title, "template": f"kit/sections/{key}.html"}
            for key, title in SECTIONS
        ],
        "swatches": SWATCHES,
        "icons": icon_names(),
        "empty_form": KitForm(prefix="empty"),
        "invalid_form": invalid_kit_form(),
        # get_page() turns ?page=abc or ?page=999 into a valid page instead of an error.
        "scholars": Paginator(rows, 5).get_page(request.GET.get("page")),
        "default_sort": "name",
        "total": len(rows),
        "statuses": samples.STATUSES,
        "clear_url": f"{reverse('kit:index')}#data",
        "crumbs": [{"label": "Scholars", "url": "#data"}, {"label": "David Shaw", "url": ""}],
        "tabs": [
            {"label": "Overview", "url": "#data", "current": True, "count": 0},
            {"label": "Documents", "url": "#data", "current": False, "count": 4},
            {"label": "History", "url": "#data", "current": False, "count": 0},
        ],
    }


@kit_only
@require_safe
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "kit/index.html", index_context(request))
