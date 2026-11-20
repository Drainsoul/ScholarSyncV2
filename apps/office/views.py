from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.awards.selectors import rollover_preview
from apps.awards.services import start_term
from apps.core.calendar import WEEKDAYS, parse_month
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.core.text import counted
from apps.office.analytics_views import summary_url
from apps.office.dashboard import office_dashboard
from apps.programs.models import AcademicTerm
from apps.programs.selectors import current_term
from apps.programs.services import add_school_year
from apps.workspace.calendar import office_calendar


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def next_school_year() -> int:
    """The year the "Add school year" button adds: after the latest, or the one containing today."""
    latest = (
        AcademicTerm.objects.order_by("-school_year_start")
        .values_list("school_year_start", flat=True)
        .first()
    )
    if latest is not None:
        return latest + 1
    today = timezone.localdate()
    return today.year if today.month >= 8 else today.year - 1


CALENDAR_ID = "office-calendar"
CALENDAR_LEGEND = [
    ("task", "Your task due"),
    ("release", "Allowance release"),
    ("opens", "Applications open"),
    ("closes", "Applications close"),
]


def _calendar_context(request: HttpRequest) -> dict[str, Any]:
    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today=today)
    return {
        "calendar": office_calendar(_actor(request), today=today, month=month),
        "calendar_id": CALENDAR_ID,
        "weekdays": WEEKDAYS,
        "legend": CALENDAR_LEGEND,
        "add_task_url": reverse("office:task-new"),
    }


class HomeView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/home.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        htmx = getattr(request, "htmx", None)
        if htmx and htmx.target == CALENDAR_ID:
            # Previous/Next month: only the calendar, without the rest of the overview.
            response: HttpResponse = TemplateResponse(
                request, f"{self.template_name}#calendar", _calendar_context(request)
            )
        else:
            response = super().get(request, *args, **kwargs)
        patch_vary_headers(response, ("HX-Request", "HX-Target"))
        return response

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        shell = shell_context(self.request, area="office")
        support_open = shell["support_open"]  # counted once, for the nav and the overview
        assert isinstance(support_open, int)
        return {
            **super().get_context_data(**kwargs),
            **shell,
            "board": office_dashboard(
                _actor(self.request), now=timezone.now(), support_open=support_open
            ),
            **_calendar_context(self.request),
            "new_task_url": reverse("office:task-new"),
            "summary_url": summary_url(
                term.school_year_start if (term := current_term()) else None
            ),
        }


class TermsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/terms.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        current = current_term()
        terms = list(AcademicTerm.objects.order_by("-sort_key"))
        start = next_school_year()
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="office"),
            "rows": [
                {
                    "term": term,
                    "can_make_current": current is None or term.sort_key > current.sort_key,
                }
                for term in terms
            ],
            "next_year_label": f"{start}–{start + 1}",
        }


class AddYearView(SuperAdminRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest) -> HttpResponse:
        start = next_school_year()
        try:
            add_school_year(actor=_actor(request), start=start)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"School year {start}–{start + 1} added.")
        return redirect("office:terms")


class MakeCurrentView(SuperAdminRequiredMixin, View):
    template_name = "office/term_current.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        term = get_object_or_404(AcademicTerm, pk=pk)
        context = {
            **shell_context(request, area="office"),
            "term": term,
            "current": current_term(),
            "preview": rollover_preview(term),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        term = get_object_or_404(AcademicTerm, pk=pk)
        try:
            result = start_term(actor=_actor(request), term=term, request=request)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("office:terms")
        withdrawn = counted(result.withdrawn, "unfinished application", "unfinished applications")
        graduated = counted(result.graduated, "scholar", "scholars")
        messages.success(
            request,
            f"{term} is now the current term. Withdrew {withdrawn}. Graduated {graduated}.",
        )
        return redirect("office:terms")
