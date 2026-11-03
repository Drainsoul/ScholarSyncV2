from typing import Any

from django.views.generic import TemplateView

from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context


class HomeView(SuperAdminRequiredMixin, TemplateView):
    template_name = "office/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **shell_context(self.request, area="office")}
