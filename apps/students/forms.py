import re
from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.utils import timezone

from apps.students.models import StudentProfile
from apps.students.services import PERSONAL_FIELDS

MIN_BIRTH_DATE = date(1900, 1, 1)
PHONE_ERROR = "Enter a mobile number like 0917 123 4567."
_PHONE = re.compile(r"^(?:\+?63|0)(9\d{9})$")


class CommaDecimalField(forms.DecimalField):
    """A decimal that accepts thousands commas ("25,000.50")."""

    def to_python(self, value: Any) -> Decimal | None:  # type: ignore[override]
        if isinstance(value, str):
            value = value.replace(",", "")
        return super().to_python(value)


class PersonalForm(forms.ModelForm):  # type: ignore[type-arg]
    is_registered_voter = forms.TypedChoiceField(
        label="Registered voter of Taguig",
        choices=[("True", "Yes"), ("False", "No")],
        coerce=lambda value: value == "True",
        empty_value=None,
        widget=forms.RadioSelect,
    )
    monthly_household_income = CommaDecimalField(
        label="Monthly household income (₱)",
        required=False,
        min_value=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )

    class Meta:
        model = StudentProfile
        fields = PERSONAL_FIELDS
        labels = {
            "sex": "Sex (as on your birth certificate)",
            "residing_since": "Living in Taguig since (year)",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
        }

    def clean_phone(self) -> str:
        phone: str = self.cleaned_data["phone"]
        if not phone:
            return ""
        match = _PHONE.match(re.sub(r"[\s\-()]", "", phone))
        if match is None:
            raise forms.ValidationError(PHONE_ERROR)
        return f"+63{match.group(1)}"

    def clean_birth_date(self) -> date | None:
        born: date | None = self.cleaned_data["birth_date"]
        if born is None:
            return None
        if born > timezone.localdate():
            raise forms.ValidationError("Your birth date can't be in the future.")
        if born < MIN_BIRTH_DATE:
            raise forms.ValidationError("Enter a birth date from 1900 onward.")
        return born

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        year = cleaned.get("residing_since")
        if year is not None and "residing_since" not in self.errors:
            this_year = timezone.localdate().year
            born = cleaned.get("birth_date")
            if born is not None and not born.year <= year <= this_year:
                self.add_error(
                    "residing_since", f"Enter a year from your birth year to {this_year}."
                )
            elif born is None and "birth_date" not in self.errors and year > this_year:
                self.add_error("residing_since", f"Enter a year up to {this_year}.")
        return cleaned
