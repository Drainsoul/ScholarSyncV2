from datetime import date

from django import forms
from django.utils import timezone

MIN_BIRTH_DATE = date(1900, 1, 1)


class StaffProfileForm(forms.Form):
    """The few details staff type in to start a profile; the student fills in the rest."""

    first_name = forms.CharField(label="First name", max_length=100)
    middle_name = forms.CharField(label="Middle name", max_length=100, required=False)
    last_name = forms.CharField(label="Last name", max_length=100)
    suffix = forms.CharField(label="Suffix", max_length=20, required=False)
    birth_date = forms.DateField(
        label="Birth date",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    email = forms.EmailField(
        label="Student's email",
        help_text="We send the invitation to claim the profile here.",
        widget=forms.EmailInput(attrs={"autocomplete": "off"}),
    )

    def clean_birth_date(self) -> date:
        born: date = self.cleaned_data["birth_date"]
        if born > timezone.localdate():
            raise forms.ValidationError("The birth date can't be in the future.")
        if born < MIN_BIRTH_DATE:
            raise forms.ValidationError("Enter a birth date from 1900 onward.")
        return born
