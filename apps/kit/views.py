"""Design kit (spec §12): every component in every state, and the key-screen mockups.

Development only: every view answers 404 unless settings.KIT_ENABLED, and pages are never indexed.
"""

import json
from collections.abc import Callable
from decimal import Decimal
from functools import wraps
from typing import Any, cast

from django.conf import settings
from django.contrib import messages
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

ICONS_DIR = settings.BASE_DIR / "frontend" / "src" / "icons"

# (section id, title); the index includes kit/sections/<id>.html for each, in order.
SECTIONS: list[tuple[str, str]] = [
    ("colour", "Colour"),
    ("type", "Type"),
    ("icons", "Icons"),
    ("controls", "Controls"),
    ("data", "Data display"),
    ("feedback", "Feedback"),
    ("overlays", "Dialogs and bulk actions"),
    ("layouts", "Layouts"),
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
        "layout_names": list(LAYOUTS),
        "bulk_rows": samples.scholars()[:4],
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


MOCKUPS: dict[str, tuple[str, str, Callable[[], dict[str, object]]]] = {
    "student-dashboard": (
        "Student dashboard",
        "kit/mockups/student_dashboard.html",
        samples.student_dashboard,
    ),
    "apply": ("Apply to a program", "kit/mockups/apply.html", samples.apply),
    "application-review": (
        "Staff application review",
        "kit/mockups/application_review.html",
        samples.application_review,
    ),
    "disbursements": ("Disbursements", "kit/mockups/disbursements.html", samples.disbursements),
    "office-dashboard": (
        "Office dashboard",
        "kit/mockups/office_dashboard.html",
        samples.office_dashboard,
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
    return render(request, template, build())
