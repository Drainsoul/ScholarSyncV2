from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.awards.selectors import rollover_preview
from apps.awards.services import start_term
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import AcademicTerm
from apps.programs.selectors import current_term
from apps.programs.services import add_school_year


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def counted(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


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


class HomeView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **shell_context(self.request, area="office")}


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
