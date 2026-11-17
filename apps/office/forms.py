from django import forms

from apps.core.text import normalize_newlines


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
