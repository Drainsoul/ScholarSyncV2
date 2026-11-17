from django import forms

from apps.accounts.models import User
from apps.core.text import normalize_newlines
from apps.programs.models import Program, ProgramMembership, School


class ProgramForm(forms.Form):
    slug = forms.SlugField(
        label="Short name for links",
        max_length=50,
        help_text=(
            "Lower-case letters, numbers and hyphens, e.g. arts-grant. It can't change later."
        ),
    )
    name = forms.CharField(label="Program name", max_length=120)
    description = forms.CharField(
        label="Description",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
    )

    def __init__(self, *args: object, creating: bool, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        if not creating:
            del self.fields["slug"]

    def clean_slug(self) -> str:
        return str(self.cleaned_data["slug"]).lower()

    def clean_description(self) -> str:
        return normalize_newlines(self.cleaned_data["description"])


class AccountForm(forms.Form):
    ROLES = (
        (User.Role.STAFF.value, "Program staff"),
        (User.Role.SUPER_ADMIN.value, "Scholarship office"),
    )

    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Role", choices=ROLES, widget=forms.RadioSelect)

    def clean_full_name(self) -> str:
        name = str(self.cleaned_data["full_name"]).strip()
        if not name:
            raise forms.ValidationError("Enter the person's full name.")
        return name


class MembershipForm(forms.Form):
    program = forms.ModelChoiceField(
        label="Program", queryset=Program.objects.order_by("name"), empty_label=None
    )
    level = forms.ChoiceField(
        label="Level",
        choices=ProgramMembership.Level.choices,
        initial=ProgramMembership.Level.STAFF,
    )


class SchoolForm(forms.Form):
    name = forms.CharField(label="School name", max_length=200)
    type = forms.ChoiceField(label="Type", choices=School.Type.choices)
    grading_scale = forms.ChoiceField(label="Grading", choices=School.Scale.choices)
    is_in_taguig = forms.BooleanField(label="In Taguig", required=False)
