from collections.abc import Sequence
from typing import Any

from django import forms

from apps.programs.models import BenefitTier

DECLARATION_LABEL = (
    "I declare that the information and documents I have given are true and complete, "
    "and I agree that the scholarship office may check them."
)


class DocumentForm(forms.Form):
    # The raw upload id: the service resolves it to the student's own ready file.
    file = forms.CharField(error_messages={"required": "Upload a file first."})


NO_FAILING_LABEL = "I have no failing, incomplete or dropped subjects this term."


class RenewalSubmitForm(forms.Form):
    """The declaration, and the no-failing-grades question when the program asks it. The tier
    is the award's, so there is no tier field and `cleaned_data["tier"]` is None."""

    declaration = forms.BooleanField(
        label=DECLARATION_LABEL,
        error_messages={"required": "Confirm the declaration to submit."},
    )

    def __init__(self, *args: Any, asks_no_failing: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if asks_no_failing:
            self.fields["declares_no_failing"] = forms.BooleanField(
                required=False, label=NO_FAILING_LABEL
            )
            self.order_fields(["declares_no_failing", "declaration"])

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        cleaned["tier"] = None
        # A checkbox can't say "no": unticked means not yet confirmed, which the checklist asks
        # for, rather than a declaration of failing grades.
        if "declares_no_failing" not in self.fields or not cleaned.get("declares_no_failing"):
            cleaned["declares_no_failing"] = None
        return cleaned


class SubmitForm(forms.Form):
    """Tier choice (radios when there are several candidates) and the declaration.

    With one candidate there is no tier field and `cleaned_data["tier"]` is that tier; with none
    it is None, and the service refuses.
    """

    declaration = forms.BooleanField(
        label=DECLARATION_LABEL,
        error_messages={"required": "Confirm the declaration to submit."},
    )

    def __init__(self, *args: Any, candidates: Sequence[BenefitTier], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.candidates = list(candidates)
        if len(self.candidates) > 1:
            self.fields["tier"] = forms.ModelChoiceField(
                queryset=BenefitTier.objects.filter(pk__in=[t.pk for t in self.candidates]),
                widget=forms.RadioSelect,
                empty_label=None,
                label="Allowance tier",
                error_messages={
                    "required": "Choose an allowance tier.",
                    "invalid_choice": "Choose one of this program's allowance tiers.",
                },
            )
            self.order_fields(["tier", "declaration"])

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if len(self.candidates) <= 1:
            cleaned["tier"] = self.candidates[0] if self.candidates else None
        return cleaned
