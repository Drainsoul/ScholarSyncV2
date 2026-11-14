from datetime import date
from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.generic import TemplateView, View

from apps.applications.models import Application, Document, DocumentFile
from apps.applications.review_selectors import (
    DEFAULT_SORT,
    STATUS_FILTERS,
    applications_for_program,
    history,
    parse_queue_filters,
    queue,
    queue_position,
    staff_application,
)
from apps.applications.selectors import document_rows
from apps.applications.views import APPLICATION_TONES, DOCUMENT_TONES
from apps.awards.selectors import other_active_awards
from apps.core.htmx import HtmxHttpRequest
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.matching.checklist import snapshot_items
from apps.programs.models import AcademicTerm, Program

PAGE_SIZE = 25
TABLE_ID = "queue-table"


class QueueView(ProgramStaffRequiredMixin, TemplateView):
    request: HtmxHttpRequest
    template_name = "review/queue.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        filters = parse_queue_filters(self.request.GET)
        paginator = Paginator(queue(self.program, filters), PAGE_SIZE)
        # get_page() turns ?page=abc or ?page=999 into a valid page instead of an error.
        page = paginator.get_page(self.request.GET.get("page"))
        terms = AcademicTerm.objects.filter(
            pk__in=applications_for_program(self.program).values("term_id")
        ).order_by("-sort_key")
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "page": page,
            "rows": [
                {"application": application, "tone": APPLICATION_TONES[application.status]}
                for application in page.object_list
            ],
            "filters": filters,
            "status_choices": [(key, label) for key, (label, _) in STATUS_FILTERS.items()],
            "terms": list(terms),
            "total": paginator.count,
            "default_sort": DEFAULT_SORT,
            # A valid ?sort= rides along with filter requests; the default needs no parameter.
            "sort": filters.sort if self.request.GET.get("sort") == filters.sort else "",
            "clear_url": reverse("review:queue", kwargs={"program": self.program.slug}),
        }

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        htmx = self.request.htmx
        if htmx and htmx.target == TABLE_ID:
            context["count_oob"] = True
            response = TemplateResponse(self.request, f"{self.template_name}#queue_table", context)
        else:
            response = TemplateResponse(self.request, self.template_name, context)
        patch_vary_headers(response, ("HX-Request", "HX-Target"))
        return response


def _evaluated_on(snapshot: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(snapshot.get("evaluated_on", "")))
    except ValueError:
        return None


def _hint(snapshot: dict[str, Any]) -> dict[str, str]:
    raw = snapshot.get("hint")
    if not isinstance(raw, dict):
        return {}
    return {"label": str(raw.get("label", "")), "reason": str(raw.get("reason", ""))}


def render_review(
    request: HttpRequest,
    program: Program,
    application: Application,
    *,
    decision_form: Any = None,
    error: str = "",
    status: int = 200,
) -> HttpResponse:
    """The review screen. The POST views reuse it to show an error or a bound form."""
    snapshot = application.match_snapshot if isinstance(application.match_snapshot, dict) else {}
    items = snapshot_items(snapshot)
    under_review = application.status == Application.Status.UNDER_REVIEW
    versions = dict(
        DocumentFile.objects.filter(document__application=application, is_current=True).values_list(
            "document_id", "version"
        )
    )
    doc_rows = document_rows(application)
    rows = [
        {
            "row": row,
            "tone": DOCUMENT_TONES[row.document.status] if row.document is not None else "neutral",
            "version": versions.get(row.document.pk, 1) if row.document is not None else 1,
        }
        for row in doc_rows
    ]
    return render(
        request,
        "review/detail.html",
        {
            **shell_context(request, area="staff", program=program),
            "program": program,
            "application": application,
            "profile": application.profile,
            "tone": APPLICATION_TONES[application.status],
            "position": queue_position(program, application),
            "other_awards": other_active_awards(application.profile, program),
            "document_rows": rows,
            "documents_total": len(rows),
            "documents_approved": sum(
                1
                for row in doc_rows
                if row.document is not None and row.document.status == Document.Status.APPROVED
            ),
            "under_review": under_review,
            "evaluated_on": _evaluated_on(snapshot),
            "checks": items,
            "rules_met": sum(1 for item in items if item["state"] == "met"),
            "rules_total": len(items),
            "hint": _hint(snapshot),
            "history": history(application),
            "decision_form": decision_form,
            "error": error,
        },
        status=status,
    )


class ReviewView(ProgramStaffRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        return render_review(request, self.program, staff_application(self.program, pk))
