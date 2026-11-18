"""Scholars across programs: the office's list and its download (spec §5, M11c)."""

from typing import Any
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.awards import exporting
from apps.awards.selectors import (
    OFFICE_SCHOLAR_TABS,
    OfficeScholarFilters,
    office_scholars,
    parse_office_scholar_filters,
)
from apps.awards.views import AWARD_TONES
from apps.core import audit
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import Program

PAGE_SIZE = 25


def _query(filters: OfficeScholarFilters, **overrides: object) -> str:
    params: dict[str, object] = {
        "status": filters.status,
        "q": filters.q,
        "program": filters.program or "",
        **overrides,
    }
    return urlencode({key: value for key, value in params.items() if value not in ("", None)})


class OfficeScholarListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/scholars.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        filters = parse_office_scholar_filters(self.request.GET)
        page = Paginator(office_scholars(filters), PAGE_SIZE).get_page(self.request.GET.get("page"))
        base = reverse("office:scholars")
        export = reverse("office:scholars-export")
        rows = [
            {
                "award": award,
                "tone": AWARD_TONES[award.status],
                # Staff screens 404 for a closed program, so its scholars get no link.
                "url": (
                    reverse(
                        "scholars:detail", kwargs={"program": award.program.slug, "pk": award.pk}
                    )
                    if award.program.is_active
                    else ""
                ),
            }
            for award in page.object_list
        ]
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="office"),
            "filters": filters,
            "page": page,
            "rows": rows,
            "programs": list(Program.objects.order_by("name")),
            "tabs": [
                {
                    "label": label,
                    "url": f"{base}?{_query(filters, status=key)}",
                    "current": key == filters.status,
                    "count": 0,
                }
                for key, label in OFFICE_SCHOLAR_TABS.items()
            ],
            "csv_url": f"{export}?{_query(filters, format='csv')}",
            "xlsx_url": f"{export}?{_query(filters, format='xlsx')}",
        }


class OfficeScholarExportView(SuperAdminRequiredMixin, View):
    """The filtered cross-program list as CSV or XLSX, built in the request (spec §7, M11c)."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        assert isinstance(user, User)
        filters = parse_office_scholar_filters(request.GET)
        fmt = "xlsx" if request.GET.get("format") == "xlsx" else "csv"
        body, content_type, filename, count = exporting.office_export_file(
            filters, fmt, today=timezone.localdate()
        )
        if request.method != "HEAD":  # a HEAD downloads nothing
            audit.record(
                actor=user,
                action="scholars.exported",
                request=request,
                # Never the name search: it is a name.
                data={
                    "scope": "office",
                    "format": fmt,
                    "status": filters.status,
                    "program": str(filters.program) if filters.program is not None else "",
                    "rows": count,
                },
            )
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response
