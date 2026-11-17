"""Staff money screens: schedules, disbursements and the budget. Views are thin."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.money import selectors, services
from apps.money.forms import ScheduleForm
from apps.money.models import DistributionSchedule
from apps.programs.models import Program


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # the staff mixin has signed them in
    return user


def _error_text(error: ValidationError) -> str:
    return " ".join(error.messages)


def money_tabs(program: Program, active: str) -> list[dict[str, object]]:
    """The "Money sections" tabs (the approved mockup)."""
    tabs = [("schedules", "Schedules", reverse("money:schedules", args=[program.slug]))]
    return [
        {"label": label, "url": url, "current": key == active, "count": 0}
        for key, label, url in tabs
    ]


def _page(request: HttpRequest, program: Program, active: str, **extra: Any) -> dict[str, Any]:
    return {
        **shell_context(request, area="staff", program=program),
        "money_tabs": money_tabs(program, active),
        **extra,
    }


class SchedulesView(ProgramStaffRequiredMixin, View):
    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        context = _page(
            request,
            self.program,
            "schedules",
            schedules=selectors.schedule_list(self.program),
        )
        return render(request, "money/schedules.html", context)


class ScheduleFormView(ProgramStaffRequiredMixin, View):
    """New schedule (no pk) or edit one."""

    def _render(
        self,
        request: HttpRequest,
        form: ScheduleForm,
        schedule: DistributionSchedule | None,
        status: int = 200,
    ) -> HttpResponse:
        context = _page(request, self.program, "schedules", form=form, schedule=schedule)
        return render(request, "money/schedule_form.html", context, status=status)

    def get(self, request: HttpRequest, program: str, pk: int | None = None) -> HttpResponse:
        schedule = selectors.staff_schedule(self.program, pk) if pk is not None else None
        initial = ScheduleForm.initial_for(schedule) if schedule is not None else None
        return self._render(request, ScheduleForm(initial=initial, program=self.program), schedule)

    def post(self, request: HttpRequest, program: str, pk: int | None = None) -> HttpResponse:
        schedule = selectors.staff_schedule(self.program, pk) if pk is not None else None
        form = ScheduleForm(request.POST, program=self.program)
        if not form.is_valid():
            return self._render(request, form, schedule, status=400)
        data = services.ScheduleData(**form.cleaned_data)
        try:
            services.save_schedule(
                actor=_actor(request),
                program=self.program,
                schedule_id=pk,
                data=data,
                request=request,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, form, schedule, status=400)
        messages.success(request, "Schedule saved.")
        return redirect("money:schedules", program=self.program.slug)


class SchedulePublishView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        published = request.POST.get("publish") == "1"
        try:
            services.set_published(
                actor=_actor(request),
                program=self.program,
                schedule_id=pk,
                published=published,
                request=request,
            )
        except ValidationError as error:
            messages.warning(request, _error_text(error))
        else:
            messages.success(
                request,
                "Published. Scholars can see this schedule." if published else "Unpublished.",
            )
        return redirect("money:schedules", program=self.program.slug)
