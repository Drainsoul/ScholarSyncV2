"""Program settings (M11b): rules and window, allowance tiers, required documents."""

from typing import Any, ClassVar

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.programs import services
from apps.programs.models import Program, ProgramMembership

from .settings_forms import RulesForm


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


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
