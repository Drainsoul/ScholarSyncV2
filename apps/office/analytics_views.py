"""Office analytics and the program summary download (spec §12, M11c)."""

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core import audit
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import Program

from .analytics import analytics, parse_analytics_filters, school_years, summary_file


def summary_url(year: int | None, fmt: str = "xlsx") -> str:
    """The program summary download; no year means the current school year."""
    base = reverse("office:analytics-export")
    return f"{base}?year={year}&format={fmt}" if year is not None else f"{base}?format={fmt}"


class AnalyticsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/analytics.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        filters = parse_analytics_filters(self.request.GET)
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="office"),
            "filters": filters,
            "board": analytics(filters, today=timezone.localdate()),
            "years": [(year, f"{year}–{year + 1}") for year in school_years()],
            "programs": list(Program.objects.order_by("name")),
            "summary_url": summary_url(filters.year),
        }


class AnalyticsExportView(SuperAdminRequiredMixin, View):
    """One row per program for a school year, built in the request (spec §7, M11c)."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        assert isinstance(user, User)
        year = parse_analytics_filters(request.GET).year
        fmt = "csv" if request.GET.get("format") == "csv" else "xlsx"
        body, content_type, filename, count = summary_file(year, fmt)
        audit.record(
            actor=user,
            action="analytics.exported",
            request=request,
            data={"format": fmt, "year": year, "rows": count},
        )
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response
