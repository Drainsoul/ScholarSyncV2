"""Sample forms for the design kit (no real data)."""

from django import forms

SCHOOLS = [
    ("", "Choose a school"),
    ("tcu", "Taguig City University"),
    ("pup", "Polytechnic University of the Philippines"),
    ("tup", "Technological University of the Philippines"),
]
YEAR_LEVELS = [("1", "1st year"), ("2", "2nd year"), ("3", "3rd year"), ("4", "4th year")]


class KitForm(forms.Form):
    full_name = forms.CharField(label="Full name", help_text="As it appears on your school ID.")
    email = forms.EmailField(label="Email address")
    school = forms.ChoiceField(label="School", choices=SCHOOLS)
    year_level = forms.ChoiceField(
        label="Year level", widget=forms.RadioSelect, choices=YEAR_LEVELS
    )
    notes = forms.CharField(label="Notes for the reviewer", widget=forms.Textarea, required=False)
    consent = forms.BooleanField(label="I agree to the privacy notice")


def invalid_kit_form() -> KitForm:
    form = KitForm(
        prefix="invalid",
        data={
            "invalid-full_name": "",
            "invalid-email": "not-an-email",
            "invalid-school": "<img src=x>",
        },
    )
    form.is_valid()
    form.add_error(None, "Check the highlighted fields, then submit again.")
    return form


class ApplyForm(forms.Form):
    declaration = forms.BooleanField(
        label="The information and documents I submit are true and complete.",
        help_text="False statements end your scholarship and may be reported to the city.",
    )


class DecisionForm(forms.Form):
    note = forms.CharField(
        label="Note to the applicant",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="They see this in their notifications and email. Required to return or reject.",
    )
