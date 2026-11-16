from typing import Any

from django import forms

from apps.awards.models import Award
from apps.programs.models import BenefitTier
from apps.programs.selectors import current_term, tiers_in_force


class AwardEditForm(forms.Form):
    student_number = forms.CharField(label="Student number", max_length=50, required=False)
    notes = forms.CharField(label="Notes", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    tier = forms.ModelChoiceField(
        label="Allowance tier",
        queryset=BenefitTier.objects.none(),
        empty_label=None,
        error_messages={"invalid_choice": "Choose one of this program's allowance tiers."},
    )

    def __init__(self, *args: Any, award: Award, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        term = current_term()
        pks = {tier.pk for tier in tiers_in_force(award.program, term)} if term else set()
        pks.add(award.tier_id)  # the award's own tier stays selectable even after a re-price
        tier_field = self.fields["tier"]
        assert isinstance(tier_field, forms.ModelChoiceField)
        tier_field.queryset = BenefitTier.objects.filter(pk__in=pks).order_by("sort_order", "name")


class StatusForm(forms.Form):
    to = forms.ChoiceField(choices=Award.Status.choices)
    reason = forms.CharField(
        label="Reason",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"max_length": "Keep the reason under 1,000 characters."},
        help_text="Staff see the reason on the scholar's record.",
    )
