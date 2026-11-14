from django import forms

from apps.applications.models import Application
from apps.applications.review import (
    MAX_DECISION_REASON,
    MAX_DECLINE_REASON,
    NEED_REJECT_REASON,
    NEED_RETURN_REASON,
)
from apps.programs.models import BenefitTier, Program
from apps.programs.selectors import tiers_in_force

APPROVE = "approve"
RETURN = "return"
REJECT = "reject"
NEED_TIER = "Choose the allowance tier."


class DeclineForm(forms.Form):
    reason = forms.CharField(
        label="Reason",
        max_length=MAX_DECLINE_REASON,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"required": "Say why you're declining this document."},
        help_text="The student reads this when you return the application.",
    )


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decision",
        choices=[(APPROVE, "Approve"), (RETURN, "Return for changes"), (REJECT, "Don't approve")],
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose a decision.",
            "invalid_choice": "Choose a decision.",
        },
    )
    tier = forms.ModelChoiceField(
        label="Allowance tier",
        queryset=BenefitTier.objects.none(),
        required=False,
        empty_label="Choose a tier",
        error_messages={"invalid_choice": "Choose one of this program's allowance tiers."},
    )
    reason = forms.CharField(
        label="Reason or note",
        max_length=MAX_DECISION_REASON,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Required to return or not approve. The student reads it when signed in.",
    )

    def __init__(self, *args: object, program: Program, application: Application, **kwargs: object):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        in_force = tiers_in_force(program, application.term)
        tier_field = self.fields["tier"]
        assert isinstance(tier_field, forms.ModelChoiceField)
        tier_field.queryset = BenefitTier.objects.filter(
            pk__in=[tier.pk for tier in in_force]
        ).order_by("sort_order", "name")
        # Preselect the requested tier only while it is still offered.
        if application.requested_tier_id in {tier.pk for tier in in_force}:
            tier_field.initial = application.requested_tier_id

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        decision = cleaned.get("decision")
        reason = str(cleaned.get("reason") or "").strip()
        if decision == APPROVE and cleaned.get("tier") is None and "tier" not in self.errors:
            self.add_error("tier", NEED_TIER)
        elif decision == RETURN and not reason and "reason" not in self.errors:
            self.add_error("reason", NEED_RETURN_REASON)
        elif decision == REJECT and not reason and "reason" not in self.errors:
            self.add_error("reason", NEED_REJECT_REASON)
        return cleaned
