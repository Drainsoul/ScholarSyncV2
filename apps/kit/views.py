"""Design kit (spec §12): every component in every state, and the key-screen mockups.

Development only: every view answers 404 unless settings.KIT_ENABLED, and pages are never indexed.
"""

import re
from collections.abc import Callable
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.core.htmx import HtmxHttpRequest, Tone, close_dialog, toast
from apps.core.templatetags.ui import peso
from apps.kit import samples
from apps.kit.forms import KitForm, invalid_kit_form

View = Callable[..., HttpResponse]

SYMBOL_ID = re.compile(r'<symbol id="([^"]+)"')

# (section id, title); the index includes kit/sections/<id>.html for each, in order.
SECTIONS: list[tuple[str, str]] = [
    ("colour", "Colour"),
    ("type", "Type"),
    ("icons", "Icons"),
    ("controls", "Controls"),
    ("data", "Data display"),
    ("feedback", "Feedback"),
    ("overlays", "Dialogs, drawer and bulk actions"),
    ("layouts", "Layouts"),
]

SWATCHES = [
    "ink-900", "slate-700", "slate-500", "slate-300", "slate-200", "slate-100", "slate-50",
    "white", "red-700", "red-800", "red-50", "blue-700", "blue-800", "blue-50", "yellow-500",
    "yellow-100", "yellow-50", "gold-700", "green-800",
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
    """Symbol ids in the built sprite (a deploy may ship no frontend/src); [] if it is missing."""
    sprite = finders.find("dist/icons.svg")
    if not isinstance(sprite, str):
        return []
    return SYMBOL_ID.findall(Path(sprite).read_text(encoding="utf-8"))


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
    sort = request.GET.get("sort", "")
    return {
        "sections": [
            {"id": key, "title": title, "template": f"kit/sections/{key}.html"}
            for key, title in SECTIONS
        ],
        "swatches": SWATCHES,
        "layout_names": list(LAYOUTS),
        "bulk_rows": samples.scholars()[:4],
        "icons": icon_names(),
        "empty_form": KitForm(prefix="empty"),
        "invalid_form": invalid_kit_form(),
        # get_page() turns ?page=abc or ?page=999 into a valid page instead of an error.
        "scholars": Paginator(rows, 5).get_page(request.GET.get("page")),
        "default_sort": "name",
        # A valid ?sort= rides along with filter requests; the default needs no parameter.
        "sort": sort if sort.removeprefix("-") in SORTS else "",
        "total": len(rows),
        "statuses": samples.STATUSES,
        "clear_url": f"{reverse('kit:index')}#data",
        "crumbs": [{"label": "Scholars", "url": "#data"}, {"label": "David Shaw", "url": ""}],
        "tabs": [
            {"label": "Overview", "url": "#data", "current": True, "count": 2},
            {"label": "Documents", "url": "#data", "current": False, "count": 4},
            {"label": "History", "url": "#data", "current": False, "count": 0},
        ],
        "figures": [
            {"label": "Active scholars", "value": "1,284"},
            {"label": "Applications waiting", "value": "96"},
            {"label": "Released this year", "value": "₱18,240,000.00"},
            {"label": "At risk", "value": "23"},
        ],
        "attention": [
            {
                "title": "12 LANI applications have waited more than 7 days",
                "detail": "Overdue: window closes 15 November",
                "tone": "danger",
                "url": "#data",
            },
            {
                "title": "3 program reports are waiting for your review",
                "detail": "Oldest sent 4 days ago",
                "tone": "warning",
                "url": "#data",
            },
            {
                "title": "LANI applications open on 3 November",
                "detail": "Starts in 4 days",
                "tone": "info",
                "url": "#data",
            },
        ],
        "drawer_scholar": samples.scholars()[0],
    }


TONE_LEVELS: dict[str, int] = {
    "info": messages.INFO,
    "success": messages.SUCCESS,
    "warning": messages.WARNING,
    "danger": messages.ERROR,
}


@kit_only
@require_safe
def index(request: HtmxHttpRequest) -> HttpResponse:
    context = index_context(request)
    if request.htmx and request.htmx.target == "scholars-table":
        context["count_oob"] = True
        response = render(request, "kit/sections/data.html#scholars_table", context)
    else:
        response = render(request, "kit/index.html", context)
    patch_vary_headers(response, ("HX-Request", "HX-Target"))
    return response


@kit_only
@require_POST
def demo_toast(request: HtmxHttpRequest) -> HttpResponse:
    message = request.POST.get("message", "").strip()[:200] or "Saved"
    tone = request.POST.get("tone", "")
    if tone not in TONE_LEVELS:
        tone = "info"
    if request.htmx:
        return toast(HttpResponse(status=204), message, cast(Tone, tone))
    messages.add_message(request, TONE_LEVELS[tone], message)
    return redirect(f"{reverse('kit:index')}#feedback")


RELEASE_AMOUNT = Decimal("60000.00")
RELEASE_COUNT = 12
BULK_VERBS = {"approve": "Approved", "return": "Returned"}


@kit_only
@require_http_methods(["GET", "POST"])
def demo_dialog(request: HtmxHttpRequest) -> HttpResponse:
    if request.method == "POST":
        text = f"Released {peso(RELEASE_AMOUNT)} to {RELEASE_COUNT} scholars"
        if request.htmx:
            return close_dialog(toast(HttpResponse(status=204), text))
        messages.success(request, text)
        return redirect(f"{reverse('kit:index')}#overlays")
    template = "kit/demo_dialog_fragment.html" if request.htmx else "kit/demo_dialog.html"
    response = render(request, template, {"amount": RELEASE_AMOUNT, "count": RELEASE_COUNT})
    patch_vary_headers(response, ("HX-Request",))
    return response


@kit_only
@require_POST
def demo_bulk(request: HtmxHttpRequest) -> HttpResponse:
    known = {str(row["id"]) for row in samples.scholars()}
    ids = [value for value in request.POST.getlist("ids") if value in known]
    verb = BULK_VERBS.get(request.POST.get("action", ""))
    tone: Tone
    if not ids:
        text, tone = "Select at least one application first.", "warning"
    elif verb is None:
        text, tone = "Choose an action for the selected applications.", "warning"
    else:
        text, tone = f"{verb} {len(ids)} application{'s' if len(ids) != 1 else ''}", "success"
    if request.htmx:
        return toast(HttpResponse(status=204), text, tone)
    messages.add_message(request, TONE_LEVELS[tone], text)
    return redirect(f"{reverse('kit:index')}#overlays")


LAYOUTS = {
    "public": "layouts/public.html",
    "auth": "layouts/auth.html",
    "student": "layouts/student.html",
    "staff": "layouts/staff.html",
    "office": "layouts/office.html",
}


@kit_only
@require_safe
def layout_demo(request: HttpRequest, name: str) -> HttpResponse:
    if name not in LAYOUTS:
        raise Http404
    context = {"layout": LAYOUTS[name], "name": name, **samples.chrome(name)}
    if name in {"staff", "office"}:
        context["crumbs"] = [
            {"label": "Design kit", "url": reverse("kit:index")},
            {"label": "Layouts", "url": ""},
        ]
    return render(request, "kit/layout_demo.html", context)


@kit_only
@require_POST
def demo_signout(request: HttpRequest) -> HttpResponse:
    messages.info(request, "Sign-out arrives with accounts in M4.")
    return redirect(f"{reverse('kit:index')}#layouts")


Build = Callable[[QueryDict], dict[str, object]]


def fixed(build: Callable[[], dict[str, object]]) -> Build:
    """A mockup whose sample data ignores the query string."""
    return lambda params: build()


def scholars_mockup(params: QueryDict) -> dict[str, object]:
    """?status= picks the tab (unknown: all); ?scholar=<id> opens the drawer (bad id: none)."""
    value = params.get("scholar", "")
    scholar = int(value) if value.isascii() and value.isdigit() else None
    return samples.scholars_page(params.get("status", "all"), scholar, params.get("page"))


MOCKUPS: dict[str, tuple[str, str, Build]] = {
    "student-dashboard": (
        "Student dashboard",
        "kit/mockups/student_dashboard.html",
        fixed(samples.student_dashboard),
    ),
    "apply": ("Apply to a program", "kit/mockups/apply.html", fixed(samples.apply)),
    "application-review": (
        "Staff application review",
        "kit/mockups/application_review.html",
        fixed(samples.application_review),
    ),
    "scholars": ("Scholars", "kit/mockups/scholars.html", scholars_mockup),
    "disbursements": (
        "Disbursements",
        "kit/mockups/disbursements.html",
        fixed(samples.disbursements),
    ),
    "office-dashboard": (
        "Office dashboard",
        "kit/mockups/office_dashboard.html",
        fixed(samples.office_dashboard),
    ),
}


@kit_only
@require_safe
def mockups(request: HttpRequest) -> HttpResponse:
    items = [{"slug": slug, "title": title} for slug, (title, _, _) in MOCKUPS.items()]
    return render(request, "kit/mockups/index.html", {"mockups": items})


@kit_only
@require_safe
def mockup(request: HttpRequest, slug: str) -> HttpResponse:
    if slug not in MOCKUPS:
        raise Http404
    _, template, build = MOCKUPS[slug]
    return render(request, template, build(request.GET))
