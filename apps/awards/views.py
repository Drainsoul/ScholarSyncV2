"""The student's scholarships: awards, term records and renewals."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.applications.renewals import RENEWAL_REJECTED, RENEWAL_SUMMER, start_renewal
from apps.awards.models import Award
from apps.awards.selectors import RenewalStatus, ScholarshipCard, scholarships_for_student
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context

AWARD_TONES: dict[str, str] = {
    Award.Status.ACTIVE: "success",
    Award.Status.SUSPENDED: "warning",
    Award.Status.INACTIVE: "neutral",
    Award.Status.GRADUATED: "info",
}


def _student(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def renewal_line(card: ScholarshipCard) -> dict[str, str]:
    """What the card says about renewing: a sentence, and the action it offers (if any)."""
    renewal, term = card.renewal, card.renewal.term
    status = renewal.status
    if status == RenewalStatus.NOT_ACTIVE:
        return {"text": f"This scholarship is {card.award.get_status_display().lower()}."}
    if status == RenewalStatus.NO_TERM:
        return {"text": card.window_reason}
    if status == RenewalStatus.SUMMER:
        return {"text": RENEWAL_SUMMER}
    if status == RenewalStatus.RENEWED:
        if term is not None and card.award.started_term_id == term.pk:
            return {"text": f"Your scholarship covers {term}."}
        return {"text": f"Renewed for {term}."}
    if status == RenewalStatus.REJECTED:
        return {"text": RENEWAL_REJECTED.format(term=term)}
    if status == RenewalStatus.OPEN:
        assert renewal.application_id is not None
        return {
            "text": f"Your renewal for {term} is in progress.",
            "action": "continue",
            "url": reverse("applications:detail", args=[renewal.application_id]),
        }
    if card.window_reason:
        return {"text": card.window_reason}
    return {
        "text": f"Your scholarship is due for renewal for {term}.",
        "action": "renew",
        "url": reverse("scholarships:renew", args=[card.award.pk]),
        "label": f"Renew for {term}",
    }


class ScholarshipsView(StudentRequiredMixin, TemplateView):
    template_name = "awards/scholarships.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        cards = scholarships_for_student(_student(self.request), today=timezone.localdate())
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "cards": [
                {
                    "card": card,
                    "tone": AWARD_TONES[card.award.status],
                    "renewal": renewal_line(card),
                }
                for card in cards
            ],
            "match_url": reverse("matching:match"),
        }


class RenewView(StudentRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        try:
            application = start_renewal(user=_student(request), award_id=pk, request=request)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("scholarships:list")
        messages.success(request, "Renewal started.")
        return redirect("applications:detail", pk=application.pk)
