from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context
from apps.matching.legacy_model import Hint
from apps.matching.selectors import ProgramMatch, match_page

HINT_PROGRAMS = {"tcu-ceaa": "TCU CEAA", "lani": "LANI"}
CHECK_ICONS = {"met": "circle-check", "unmet": "circle-alert", "missing": "circle-help"}


def hint_sentence(hint: Hint) -> str:
    name = HINT_PROGRAMS.get(hint.program_slug or "", "no program")
    merit = ", with merit" if hint.merit else ""
    return f"v1's model suggests {name}{merit} ({round(hint.probability * 100)}%)."


def _card(match: ProgramMatch) -> dict[str, Any]:
    items = [
        {
            "state": check.state.value,
            "icon": CHECK_ICONS[check.state.value],
            "text": check.text,
            "detail": check.reason,
            "url": reverse(check.fix_url_name) if check.fix_url_name else "",
            "url_label": "Fix this in your profile",
        }
        for check in match.result.checks
    ]
    return {"match": match, "items": items}


class MatchView(StudentRequiredMixin, TemplateView):
    template_name = "matching/match.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        request: HttpRequest = self.request
        user = request.user
        assert isinstance(user, User)
        page = match_page(user, today=timezone.localdate())
        hint = page.hint
        return {
            **super().get_context_data(**kwargs),
            **shell_context(request, area="student"),
            "profile_url": reverse("students:profile"),
            "page": page,
            "cards": [_card(match) for match in page.matches],
            "hint_text": hint_sentence(hint) if isinstance(hint, Hint) else hint,
        }
