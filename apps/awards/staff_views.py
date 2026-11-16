"""Staff screens for a program's scholars."""

from typing import Any
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.awards.models import Award
from apps.awards.selectors import (
    DEFAULT_SCHOLAR_TAB,
    SCHOLAR_TABS,
    Renewal,
    RenewalStatus,
    ScholarFilters,
    at_risk_reasons,
    parse_scholar_filters,
    renewal_for,
    scholars,
    staff_award,
)
from apps.awards.views import AWARD_TONES
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import application_term, window_state

PAGE_SIZE = 25


def staff_renewal_text(renewal: Renewal, program: Program, today: Any) -> str:
    """Where the scholar stands on renewing, for staff."""
    term = renewal.term
    status = renewal.status
    if status == RenewalStatus.NOT_ACTIVE:
        return "Not active, so no renewal is due."
    if status == RenewalStatus.NO_TERM:
        return "No current term is set."
    if status == RenewalStatus.SUMMER:
        return "No renewal in the summer term."
    if status == RenewalStatus.RENEWED:
        return f"Renewed for {term}."
    if status == RenewalStatus.REJECTED:
        return f"Renewal not approved for {term}."
    if status == RenewalStatus.OPEN:
        return f"Renewal in progress for {term}."
    if window_state(program, today) != "open":
        return f"Due to renew for {term}. Renewals are closed."
    return f"Due to renew for {term}."


def _query(filters: ScholarFilters, **overrides: str) -> str:
    params = {"status": filters.status, "q": filters.q, "tier": filters.tier, **overrides}
    if params["status"] == DEFAULT_SCHOLAR_TAB:
        params.pop("status")
    return urlencode({key: value for key, value in params.items() if value})


def drawer_for(
    program: Program, raw: str, term: AcademicTerm | None, today: Any
) -> dict[str, Any] | None:
    """The drawer for `?scholar=<id>`; anything not one of the program's awards opens nothing."""
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        return None
    try:
        award = staff_award(program, int(raw))
    except Http404:
        return None
    return {
        "award": award,
        "tone": AWARD_TONES[award.status],
        "renewal": staff_renewal_text(renewal_for(award, term), program, today),
        "at_risk": at_risk_reasons(award, program, term, today),
    }


class ScholarListView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "scholars/list.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        today = timezone.localdate()
        term = application_term(today)
        filters = parse_scholar_filters(self.request.GET, self.program)
        rows = scholars(self.program, filters, term=term, today=today)
        page = Paginator(rows, PAGE_SIZE).get_page(self.request.GET.get("page"))
        base = reverse("scholars:list", kwargs={"program": self.program.slug})
        list_query = _query(filters, page=str(page.number) if page.number > 1 else "")
        tiers = (
            self.program.tiers.order_by("code", "sort_order").values_list("code", "name").distinct()
        )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "term": term,
            "filters": filters,
            "page": page,
            "rows": [
                {"award": award, "tone": AWARD_TONES[award.status]} for award in page.object_list
            ],
            "tabs": [
                {
                    "label": label,
                    "url": f"{base}?{_query(filters, status=key)}"
                    if _query(filters, status=key)
                    else base,
                    "current": key == filters.status,
                }
                for key, label in SCHOLAR_TABS.items()
            ],
            "tiers": list(dict(tiers).items()),
            "list_url": base,
            "list_query": list_query,
            "drawer": drawer_for(self.program, self.request.GET.get("scholar", ""), term, today),
            "close_url": f"{base}?{list_query}" if list_query else base,
            "statuses": Award.Status,
        }
