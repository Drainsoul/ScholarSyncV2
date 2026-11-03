from typing import Any, cast

from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import home_url_for, shell_context


class DashboardView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "workspace/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
        }


class NoProgramsView(TemplateView):
    """Staff who belong to no program yet. Everyone else is sent to their own home."""

    template_name = "workspace/no_programs.html"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        assert isinstance(user, User)
        home = home_url_for(user)
        if home != request.path:
            return redirect(home)
        return cast(HttpResponse, super().dispatch(request, *args, **kwargs))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **shell_context(self.request, area="staff")}
