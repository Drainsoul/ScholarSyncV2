import re
from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.files.models import StoredFile
from apps.files.selectors import usable_file
from apps.programs.models import School
from apps.students.models import EducationRecord, FamilyMember, StudentProfile
from apps.students.services import PERSONAL_FIELDS

MIN_BIRTH_DATE = date(1900, 1, 1)
PHONE_ERROR = "Enter a mobile number like 0917 123 4567."
_PHONE = re.compile(r"^(?:\+?63|0)(9\d{9})$")


def normalise_phone(phone: str) -> str:
    """A Philippine mobile number as +639XXXXXXXXX; blank stays blank."""
    if not phone:
        return ""
    match = _PHONE.match(re.sub(r"[\s\-()]", "", phone))
    if match is None:
        raise forms.ValidationError(PHONE_ERROR)
    return f"+63{match.group(1)}"


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
        return normalise_phone(self.cleaned_data["phone"])

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


class FamilyMemberForm(forms.Form):
    relation = forms.ChoiceField(choices=FamilyMember.Relation.choices)
    name = forms.CharField(max_length=200)
    occupation = forms.CharField(max_length=100, required=False)
    monthly_income = CommaDecimalField(
        label="Monthly income (₱)",
        required=False,
        min_value=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    contact = forms.CharField(
        label="Contact number",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "off"}),
    )

    def clean_contact(self) -> str:
        return normalise_phone(self.cleaned_data["contact"])


MIN_YEAR = 1950
YEARS_AHEAD = 6
GWA_RANGES = {
    School.Scale.PERCENT: (Decimal("50"), Decimal("100"), "Enter a GWA from 50 to 100."),
    School.Scale.ONE_TO_FIVE: (
        Decimal("1"),
        Decimal("5"),
        "Enter a GWA from 1.00 to 5.00.",
    ),
    School.Scale.FOUR_POINT: (
        Decimal("0"),
        Decimal("4"),
        "Enter a GWA from 0.00 to 4.00.",
    ),
}
YEAR_LEVELS = {
    EducationRecord.Level.ELEMENTARY: (1, 6),
    EducationRecord.Level.JHS: (7, 10),
    EducationRecord.Level.SHS: (11, 12),
    EducationRecord.Level.COLLEGE: (1, 5),
}


class EducationForm(forms.Form):
    level = forms.ChoiceField(choices=EducationRecord.Level.choices)
    school = forms.ModelChoiceField(
        queryset=School.objects.all(), required=False, empty_label="My school isn't listed"
    )
    school_name = forms.CharField(label="School name", max_length=200, required=False)
    school_type = forms.ChoiceField(
        label="School type", choices=[("", "---------"), *School.Type.choices], required=False
    )
    gwa_scale = forms.ChoiceField(
        label="Grading scale", choices=[("", "---------"), *School.Scale.choices], required=False
    )
    course = forms.CharField(max_length=200, required=False)
    year_level = forms.IntegerField(min_value=0, max_value=99, required=False)
    gwa = forms.DecimalField(
        label="GWA", max_digits=5, decimal_places=2, required=False, localize=False
    )
    units = forms.IntegerField(min_value=0, max_value=1000, required=False)
    year_from = forms.IntegerField(label="From (year)", required=False)
    year_to = forms.IntegerField(label="To (year)", required=False)
    is_current = forms.BooleanField(label="I'm studying here now", required=False)

    def _check_year(self, name: str, latest: int) -> None:
        year = self.cleaned_data.get(name)
        if year is not None and not MIN_YEAR <= year <= latest:
            self.add_error(name, f"Enter a year from {MIN_YEAR} to {latest}.")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        school = cleaned.get("school")
        name = (cleaned.get("school_name") or "").strip()
        cleaned["school_name"] = name
        if school is None and not name:
            if "school" not in self.errors:
                raise forms.ValidationError("Choose your school or type its name.")
        elif school is not None and name:
            raise forms.ValidationError("Choose a school from the list or type a name, not both.")

        if school is None and name:
            for field in ("school_type", "gwa_scale"):
                if not cleaned.get(field) and field not in self.errors:
                    self.add_error(field, "This field is required.")
        scale = school.grading_scale if school is not None else cleaned.get("gwa_scale")

        gwa = cleaned.get("gwa")
        if gwa is not None and "gwa" not in self.errors:
            if not scale:
                if "gwa_scale" not in self.errors:
                    self.add_error("gwa_scale", "Choose the grading scale for your GWA.")
            else:
                low, high, message = GWA_RANGES[School.Scale(scale)]
                if not low <= gwa <= high:
                    self.add_error("gwa", message)

        level = cleaned.get("level")
        year_level = cleaned.get("year_level")
        if level == EducationRecord.Level.ALS:
            cleaned["year_level"] = None
        elif year_level is not None and level and "year_level" not in self.errors:
            low_year, high_year = YEAR_LEVELS[EducationRecord.Level(level)]
            if not low_year <= year_level <= high_year:
                self.add_error("year_level", f"Enter a year level from {low_year} to {high_year}.")

        latest = timezone.localdate().year + YEARS_AHEAD
        self._check_year("year_from", latest)
        self._check_year("year_to", latest)
        start, end = cleaned.get("year_from"), cleaned.get("year_to")
        if (
            start is not None
            and end is not None
            and not {"year_from", "year_to"} & set(self.errors)
            and start > end
        ):
            self.add_error("year_to", "The end year can't be before the start year.")
        return cleaned


class PhotoForm(forms.Form):
    photo = forms.CharField(required=False)

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_photo(self) -> StoredFile:
        file = usable_file(self.user, self.cleaned_data["photo"], "photo")
        if file is None:
            raise forms.ValidationError("Upload the photo again.")
        return file
