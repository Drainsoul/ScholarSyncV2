"""Program settings (M11b): rules and window, allowance tiers, required documents."""

from typing import Any, ClassVar

from allauth.account.decorators import reauthentication_required
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.programs import services
from apps.programs.models import Program, ProgramMembership
from apps.programs.selectors import TierLine, current_term, tier_codes

from .settings_forms import RulesForm, TierChangeForm, TierForm


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _form_errors(form: forms.Form, error: ValidationError) -> None:
    """A service refusal on the form: field errors where the field exists, else on top."""
    if hasattr(error, "error_dict"):
        for field, problems in error.message_dict.items():
            form.add_error(field if field in form.fields else None, problems)
    else:
        form.add_error(None, error)


class SettingsMixin(ProgramStaffRequiredMixin):
    """Heads of the program (staff get 403), and the office, which also reaches a program before
    it opens (`office_sees_inactive`); a head of a closed program gets 404 like every staff page.
    Services re-check with `require_settings_editor`."""

    level: ClassVar[ProgramMembership.Level] = ProgramMembership.Level.HEAD
    office_sees_inactive: ClassVar[bool] = True
    tab: ClassVar[str] = "rules"

    def settings_context(self, request: HttpRequest) -> dict[str, Any]:
        return {**shell_context(request, area="staff", program=self.program), "tab": self.tab}


class RulesView(SettingsMixin, View):
    template_name = "programs/settings/rules.html"

    def _render(self, request: HttpRequest, form: RulesForm) -> HttpResponse:
        context = {**self.settings_context(request), "form": form}
        return render(request, self.template_name, context)

    def _form(self, request: HttpRequest | None = None) -> RulesForm:
        # A separate copy: a bound ModelForm writes into its instance while validating, and the
        # service compares the saved program with the new values.
        instance = Program.objects.get(pk=self.program.pk)
        return RulesForm(request.POST if request else None, instance=instance)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request, self._form())

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = self._form(request)
        if not form.is_valid():
            return self._render(request, form)
        services.update_rules(
            actor=_actor(request), program=self.program, data=form.cleaned_data, request=request
        )
        messages.success(request, "Rules saved.")
        return redirect("settings:rules", program=self.program.slug)


class TiersView(SettingsMixin, View):
    tab = "tiers"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        term = current_term()
        context = {
            **self.settings_context(request),
            "lines": tier_codes(self.program, term),
            "current": term,
        }
        return render(request, "programs/settings/tiers.html", context)


@method_decorator(reauthentication_required, name="post")
class TierNewView(SettingsMixin, View):
    tab = "tiers"

    def _render(self, request: HttpRequest, form: TierForm) -> HttpResponse:
        context = {**self.settings_context(request), "form": form, "line": None}
        return render(request, "programs/settings/tier_form.html", context)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request, TierForm())

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = TierForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        try:
            services.add_tier(
                actor=_actor(request), program=self.program, request=request, **form.cleaned_data
            )
        except ValidationError as error:
            _form_errors(form, error)
            return self._render(request, form)
        messages.success(request, "Tier added.")
        return redirect("settings:tiers", program=self.program.slug)


@method_decorator(reauthentication_required, name="post")
class TierChangeView(SettingsMixin, View):
    tab = "tiers"

    def _line(self, code: str) -> TierLine:
        lines = tier_codes(self.program, current_term())
        line = next((line for line in lines if line.code == code), None)
        if line is None:
            raise Http404("No such tier.")
        return line

    def _render(self, request: HttpRequest, line: TierLine, form: TierChangeForm) -> HttpResponse:
        context = {**self.settings_context(request), "form": form, "line": line}
        return render(request, "programs/settings/tier_form.html", context)

    def get(self, request: HttpRequest, program: str, code: str) -> HttpResponse:
        line = self._line(code)
        initial: dict[str, object] = {}
        if line.in_force is not None:
            initial = {
                "base_amount": line.in_force.base_amount,
                "merit_amount": line.in_force.merit_amount,
            }
        return self._render(request, line, TierChangeForm(initial=initial))

    def post(self, request: HttpRequest, program: str, code: str) -> HttpResponse:
        line = self._line(code)
        form = TierChangeForm(request.POST)
        if not form.is_valid():
            return self._render(request, line, form)
        data = form.cleaned_data
        term = data["effective_from"]
        try:
            if data["action"] == "stop":
                services.stop_tier(
                    actor=_actor(request),
                    program=self.program,
                    code=code,
                    effective_from=term,
                    request=request,
                )
                message = f"{line.name} stops from {term}."
            else:
                services.change_tier_amounts(
                    actor=_actor(request),
                    program=self.program,
                    code=code,
                    base_amount=data["base_amount"],
                    merit_amount=data["merit_amount"],
                    effective_from=term,
                    request=request,
                )
                message = f"New amounts saved from {term}."
        except ValidationError as error:
            _form_errors(form, error)
            return self._render(request, line, form)
        messages.success(request, message)
        return redirect("settings:tiers", program=self.program.slug)
