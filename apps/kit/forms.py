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
    tier = forms.ChoiceField(
        label="Benefit tier",
        choices=[
            ("basic", "Basic, ₱5,000.00 a term"),
            ("priority", "Priority, ₱7,500.00 a term"),
            ("honors", "Honors, ₱10,000.00 a term"),
        ],
        initial="priority",
    )
    note = forms.CharField(
        label="Message to the applicant",
        widget=forms.Textarea,
        required=False,
        help_text="Required when you return or reject an application. The applicant sees it.",
    )
