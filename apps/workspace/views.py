from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
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
from apps.core.calendar import WEEKDAYS, parse_month
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import home_url_for, shell_context
from apps.programs.models import Program
from apps.students import services
from apps.students.selectors import unclaimed_profiles_for
from apps.workspace.calendar import staff_calendar
from apps.workspace.dashboard import staff_dashboard
from apps.workspace.forms import StaffProfileForm
from apps.workspace.tasks import task_status

CALENDAR_ID = "staff-calendar"
CALENDAR_LEGEND = [
    ("task", "Your task due"),
    ("release", "Allowance release"),
    ("opens", "Applications open"),
    ("closes", "Applications close"),
]


def _calendar_context(request: HttpRequest, program: Program, user: User) -> dict[str, Any]:
    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today=today)
    return {
        "calendar": staff_calendar(program, user, today=today, month=month),
        "calendar_id": CALENDAR_ID,
        "weekdays": WEEKDAYS,
        "legend": CALENDAR_LEGEND,
        "add_task_url": reverse("workspace:task-new", kwargs={"program": program.slug}),
    }


class DashboardView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "workspace/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        user = self.request.user
        assert isinstance(user, User)
        board = staff_dashboard(self.program, user, now=timezone.now())
        today = timezone.localdate()
        task_rows = []
        for task in board.tasks:
            status = task_status(task, today)
            due = f"Due {task.due_on.day} {task.due_on:%b %Y}" if task.due_on else ""
            task_rows.append(
                {
                    "title": task.title,
                    "detail": status[1] if status else (due or "No due date"),
                    "tone": status[0] if status else "neutral",
                    "url": reverse(
                        "workspace:task-edit", kwargs={"program": self.program.slug, "pk": task.pk}
                    ),
                }
            )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            **_calendar_context(self.request, self.program, user),
            "board": board,
            "task_rows": task_rows,
        }

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        htmx = getattr(request, "htmx", None)
        if htmx and htmx.target == CALENDAR_ID:
            # Previous/Next month: only the calendar, without the rest of the dashboard.
            user = request.user
            assert isinstance(user, User)
            response: HttpResponse = TemplateResponse(
                request,
                f"{self.template_name}#calendar",
                {"program": self.program, **_calendar_context(request, self.program, user)},
            )
        else:
            response = super().get(request, *args, **kwargs)
        patch_vary_headers(response, ("HX-Request", "HX-Target"))
        return response


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
