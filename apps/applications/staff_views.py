from typing import Any

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.generic import TemplateView

from apps.applications.review_selectors import (
    DEFAULT_SORT,
    STATUS_FILTERS,
    applications_for_program,
    parse_queue_filters,
    queue,
)
from apps.applications.views import APPLICATION_TONES
from apps.core.htmx import HtmxHttpRequest
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import AcademicTerm

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
