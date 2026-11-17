from decimal import Decimal
from typing import Any

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.programs.models import Program, School

PERCENT = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
ONE_TO_FIVE = [MinValueValidator(Decimal("1.00")), MaxValueValidator(Decimal("5.00"))]
UNITS = [MinValueValidator(1), MaxValueValidator(40)]

RULE_FIELDS = (
    "applications_open_on",
    "applications_close_on",
    "min_gwa_percent",
    "max_gwa_one_to_five",
    "min_units",
    "min_residency_years",
    "requires_registered_voter",
    "allowed_school_types",
    "allowed_schools",
    "renewal_min_gwa_percent",
    "renewal_max_gwa_one_to_five",
    "renewal_min_units",
    "renewal_no_failing_grades",
    "merit_min_gwa_percent",
    "merit_max_gwa_one_to_five",
    "max_terms",
    "claim_location_default",
)

FIELDSETS = (
    ("Applications window", ("applications_open_on", "applications_close_on")),
    (
        "New applicants",
        (
            "min_gwa_percent",
            "max_gwa_one_to_five",
            "min_units",
            "min_residency_years",
            "requires_registered_voter",
            "allowed_school_types",
            "allowed_schools",
        ),
    ),
    (
        "Renewal",
        (
            "renewal_min_gwa_percent",
            "renewal_max_gwa_one_to_five",
            "renewal_min_units",
            "renewal_no_failing_grades",
        ),
    ),
    ("Merit", ("merit_min_gwa_percent", "merit_max_gwa_one_to_five")),
    ("Other", ("max_terms", "claim_location_default")),
)

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class RulesForm(forms.ModelForm):  # type: ignore[type-arg]
    """A program's rules. Blank means no rule; percent is 0–100 and the 1–5 scale 1.00–5.00."""

    allowed_school_types = forms.MultipleChoiceField(
        label="Allowed school types",
        choices=School.Type.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave all unticked to allow every type.",
    )
    allowed_schools = forms.ModelMultipleChoiceField(
        label="Allowed schools",
        queryset=School.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave all unticked to allow every school.",
    )

    class Meta:
        model = Program
        fields = RULE_FIELDS
        labels = {
            "applications_open_on": "Applications open on",
            "applications_close_on": "Applications close on",
            "min_gwa_percent": "Lowest GWA (percent)",
            "max_gwa_one_to_five": "Highest GWA (1–5 scale)",
            "min_units": "Fewest units",
            "min_residency_years": "Years living in Taguig",
            "requires_registered_voter": "Must be a registered voter",
            "renewal_min_gwa_percent": "Lowest GWA to renew (percent)",
            "renewal_max_gwa_one_to_five": "Highest GWA to renew (1–5 scale)",
            "renewal_min_units": "Fewest units to renew",
            "renewal_no_failing_grades": "No failing grades to renew",
            "merit_min_gwa_percent": "Lowest GWA for merit (percent)",
            "merit_max_gwa_one_to_five": "Highest GWA for merit (1–5 scale)",
            "max_terms": "Most terms a scholar can hold",
            "claim_location_default": "Usual claim location",
        }
        widgets = {"applications_open_on": DATE, "applications_close_on": DATE}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name in ("min_gwa_percent", "renewal_min_gwa_percent", "merit_min_gwa_percent"):
            self.fields[name].validators.extend(PERCENT)
        for name in (
            "max_gwa_one_to_five",
            "renewal_max_gwa_one_to_five",
            "merit_max_gwa_one_to_five",
        ):
            self.fields[name].validators.extend(ONE_TO_FIVE)
        for name in ("min_units", "renewal_min_units"):
            self.fields[name].validators.extend(UNITS)
        self.fields["min_residency_years"].validators.append(MaxValueValidator(50))
        self.fields["max_terms"].validators.extend([MinValueValidator(1), MaxValueValidator(20)])

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        opens, closes = data.get("applications_open_on"), data.get("applications_close_on")
        if opens and closes and closes < opens:
            self.add_error("applications_close_on", "The close date can't be before the open date.")
        return data

    def fieldsets(self) -> list[tuple[str, list[forms.BoundField]]]:
        return [(title, [self[name] for name in names]) for title, names in FIELDSETS]
