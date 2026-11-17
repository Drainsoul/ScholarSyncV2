"""Program settings (M11b): rules and window, allowance tiers, required documents."""

from typing import Any, ClassVar

from django.http import HttpRequest
from django.views.generic import TemplateView

from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import ProgramMembership


class SettingsMixin(ProgramStaffRequiredMixin):
    """Heads of the program (staff get 403), and the office, which also reaches a program before
    it opens (`office_sees_inactive`); a head of a closed program gets 404 like every staff page.
    Services re-check with `require_settings_editor`."""

    level: ClassVar[ProgramMembership.Level] = ProgramMembership.Level.HEAD
    office_sees_inactive: ClassVar[bool] = True
    tab: ClassVar[str] = "rules"

    def settings_context(self, request: HttpRequest) -> dict[str, Any]:
        return {**shell_context(request, area="staff", program=self.program), "tab": self.tab}


class RulesView(SettingsMixin, TemplateView):
    template_name = "programs/settings/rules.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **self.settings_context(self.request)}
