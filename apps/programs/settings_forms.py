from decimal import Decimal
from typing import Any

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.core.text import normalize_newlines
from apps.files.policy import JPEG, MB, PDF, PNG
from apps.programs.models import AcademicTerm, Program, RequiredDocument, School
from apps.programs.selectors import current_term

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


AMOUNT = [MinValueValidator(Decimal("0"))]


class _TermField(forms.ModelChoiceField):  # type: ignore[type-arg]
    def label_from_instance(self, obj: Any) -> str:
        return str(obj)


def _term_field() -> _TermField:
    """Every term validates (so a past one gets the service's sentence); only the current term
    and later ones are offered."""
    field = _TermField(
        label="Starting from",
        queryset=AcademicTerm.objects.order_by("sort_key"),
        empty_label=None,
    )
    current = current_term()
    if current is not None:
        field.widget.choices = [
            (term.pk, str(term))
            for term in AcademicTerm.objects.filter(sort_key__gte=current.sort_key).order_by(
                "sort_key"
            )
        ]
    return field


class TierForm(forms.Form):
    code = forms.SlugField(label="Code", max_length=40, help_text="e.g. honors. It can't change.")
    name = forms.CharField(label="Name", max_length=80)
    base_amount = forms.DecimalField(
        label="Allowance per term (₱)", max_digits=12, decimal_places=2, validators=AMOUNT
    )
    merit_amount = forms.DecimalField(
        label="Allowance with merit (₱)",
        max_digits=12,
        decimal_places=2,
        validators=AMOUNT,
        initial=Decimal("0"),
        help_text="The full amount with merit, not an extra. 0 means no merit amount.",
    )
    sort_order = forms.IntegerField(label="Order on lists", min_value=0, max_value=999, initial=0)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["effective_from"] = _term_field()

    def clean_code(self) -> str:
        return str(self.cleaned_data["code"]).lower()


class TierChangeForm(forms.Form):
    ACTIONS = (("change", "Change the amounts"), ("stop", "Stop offering this tier"))

    action = forms.ChoiceField(
        label="What to do", choices=ACTIONS, widget=forms.RadioSelect, initial="change"
    )
    base_amount = forms.DecimalField(
        label="Allowance per term (₱)",
        max_digits=12,
        decimal_places=2,
        validators=AMOUNT,
        required=False,
    )
    merit_amount = forms.DecimalField(
        label="Allowance with merit (₱)",
        max_digits=12,
        decimal_places=2,
        validators=AMOUNT,
        required=False,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["effective_from"] = _term_field()

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if data.get("action") == "change":
            if data.get("base_amount") is None:
                self.add_error("base_amount", "Enter the allowance per term.")
            if data.get("merit_amount") is None:
                data["merit_amount"] = Decimal("0")
        return data


TYPE_CHOICES = ((PDF, "PDF"), (JPEG, "JPEG photo"), (PNG, "PNG image"))


class DocumentForm(forms.Form):
    code = forms.SlugField(label="Code", max_length=40, help_text="e.g. grades. It can't change.")
    label = forms.CharField(label="Document", max_length=200)
    help_text = forms.CharField(
        label="Help for students",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 2000}),
    )
    applies_to = forms.ChoiceField(label="Asked of", choices=RequiredDocument.AppliesTo.choices)
    is_required = forms.BooleanField(label="Required", required=False, initial=True)
    accepted_types = forms.MultipleChoiceField(
        label="Accepted file types",
        choices=TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        initial=[PDF, JPEG, PNG],
        error_messages={"required": "Pick at least one file type."},
    )
    max_mb = forms.IntegerField(label="Max size (MB)", min_value=1, max_value=10, initial=10)
    sort_order = forms.IntegerField(label="Order on lists", min_value=0, max_value=999, initial=0)

    def __init__(self, *args: Any, creating: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not creating:
            del self.fields["code"]

    def clean_code(self) -> str:
        return str(self.cleaned_data["code"]).lower()

    def clean_help_text(self) -> str:
        return normalize_newlines(self.cleaned_data["help_text"])

    def document_data(self) -> dict[str, Any]:
        """The cleaned values as `RequiredDocument` fields (size in bytes)."""
        data = dict(self.cleaned_data)
        data["max_bytes"] = data.pop("max_mb") * MB
        return data
