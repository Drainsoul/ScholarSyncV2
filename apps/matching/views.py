from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context
from apps.matching.checklist import checklist_items
from apps.matching.selectors import ProgramMatch, match_page


def _card(match: ProgramMatch) -> dict[str, Any]:
    items = checklist_items(match.result)
    return {"match": match, "items": items}


class MatchView(StudentRequiredMixin, TemplateView):
    template_name = "matching/match.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        request: HttpRequest = self.request
        user = request.user
        assert isinstance(user, User)
        page = match_page(user, today=timezone.localdate())
        return {
            **super().get_context_data(**kwargs),
            **shell_context(request, area="student"),
            "profile_url": reverse("students:profile"),
            "page": page,
            "cards": [_card(match) for match in page.matches],
        }
