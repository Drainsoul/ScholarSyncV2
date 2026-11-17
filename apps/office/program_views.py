from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs import services
from apps.programs.models import Program

from .dashboard import window_text
from .forms import ProgramForm

TABS = {"all": "All", "active": "Active", "inactive": "Inactive"}


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _form_errors(form: ProgramForm, error: ValidationError) -> None:
    if hasattr(error, "error_dict"):
        for field, problems in error.message_dict.items():
            form.add_error(field if field in form.fields else None, problems)
    else:
        form.add_error(None, error)


class ProgramListView(SuperAdminRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        tab = request.GET.get("tab", "all")
        if tab not in TABS:
            tab = "all"
        programs = Program.objects.order_by("name")
        if tab != "all":
            programs = programs.filter(is_active=tab == "active")
        today = timezone.localdate()
        base = reverse("office:programs")
        context: dict[str, Any] = {
            **shell_context(request, area="office"),
            "rows": [
                {"program": program, "window": window_text(program, today)} for program in programs
            ],
            "tab": tab,
            "tabs": [
                {
                    "label": label,
                    "url": base if key == "all" else f"{base}?tab={key}",
                    "current": key == tab,
                    "count": 0,
                }
                for key, label in TABS.items()
            ],
        }
        return render(request, "office/programs/list.html", context)


class ProgramNewView(SuperAdminRequiredMixin, View):
    def _render(self, request: HttpRequest, form: ProgramForm) -> HttpResponse:
        context = {**shell_context(request, area="office"), "form": form, "program": None}
        return render(request, "office/programs/form.html", context)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, ProgramForm(creating=True))

    def post(self, request: HttpRequest) -> HttpResponse:
        form = ProgramForm(request.POST, creating=True)
        if not form.is_valid():
            return self._render(request, form)
        try:
            program = services.create_program(
                actor=_actor(request), request=request, **form.cleaned_data
            )
        except ValidationError as error:
            _form_errors(form, error)
            return self._render(request, form)
        messages.success(
            request, f"{program.name} created. Set it up, then open it from the Programs page."
        )
        return redirect("settings:rules", program=program.slug)


class ProgramEditView(SuperAdminRequiredMixin, View):
    def _render(self, request: HttpRequest, program: Program, form: ProgramForm) -> HttpResponse:
        context = {**shell_context(request, area="office"), "form": form, "program": program}
        return render(request, "office/programs/form.html", context)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        program = get_object_or_404(Program, pk=pk)
        initial = {"name": program.name, "description": program.description}
        return self._render(request, program, ProgramForm(initial=initial, creating=False))

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        program = get_object_or_404(Program, pk=pk)
        form = ProgramForm(request.POST, creating=False)
        if not form.is_valid():
            return self._render(request, program, form)
        services.update_program(
            actor=_actor(request), program=program, request=request, **form.cleaned_data
        )
        messages.success(request, "Program saved.")
        return redirect("office:programs")


class ProgramActiveView(SuperAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        program = get_object_or_404(Program, pk=pk)
        active = request.POST.get("active") == "1"
        try:
            services.set_program_active(
                actor=_actor(request), program=program, active=active, request=request
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request, f"{program.name} is open." if active else f"{program.name} is closed."
            )
        return redirect("office:programs")
