from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import home_url_for, shell_context
from apps.students import services
from apps.students.selectors import unclaimed_profiles_for
from apps.workspace.forms import StaffProfileForm


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


class StudentListView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "workspace/students/list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "profiles": list(unclaimed_profiles_for(self.program)),
            "now": timezone.now(),
        }


class StudentCreateView(ProgramStaffRequiredMixin, View):
    template_name = "workspace/students/new.html"

    def _render(self, request: HttpRequest, form: StaffProfileForm) -> HttpResponse:
        context = {**shell_context(request, area="staff", program=self.program), "form": form}
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request, StaffProfileForm())

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = StaffProfileForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        actor = request.user
        assert isinstance(actor, User)
        try:
            services.create_staff_profile(actor=actor, program=self.program, **form.cleaned_data)
        except ValidationError as error:
            form.add_error("email", error)
            return self._render(request, form)
        messages.success(request, "Profile created and invitation sent.")
        return redirect("workspace:students", program=self.program.slug)


class StudentInviteView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, program: str, profile_id: int) -> HttpResponse:
        profile = get_object_or_404(unclaimed_profiles_for(self.program), pk=profile_id)
        actor = request.user
        assert isinstance(actor, User)
        # Imported profiles (M9b) have never been invited: their first invite takes an address.
        first = not profile.invites.exists()
        email = request.POST.get("email", "").strip() or None
        try:
            services.issue_invite(actor=actor, profile=profile, email=email if first else None)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Invitation sent." if first else "Invitation sent again.")
        return redirect("workspace:students", program=self.program.slug)
