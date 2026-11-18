from typing import Any

from django import forms

from apps.accounts.models import User
from apps.core.text import normalize_newlines
from apps.files.models import StoredFile
from apps.files.selectors import usable_file

from .services import NEED_PDF, PERIOD_ORDER

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
DESCRIPTION_MAX = 2000
NOTE_MAX = 1000


def _fit(value: str, limit: int) -> str:
    """Store LF, then check the length: a text that fit the box (CRLF counted as one) fits."""
    text = normalize_newlines(value)
    if len(text) > limit:
        raise forms.ValidationError(
            f"Ensure this value has at most {limit:,} characters (it has {len(text):,})."
        )
    return text


class ReportForm(forms.Form):
    """Send a report, or fix and send a returned one (the file is optional then)."""

    title = forms.CharField(label="Title", max_length=200)
    period_start = forms.DateField(label="Period from", widget=DATE)
    period_end = forms.DateField(label="Period to", widget=DATE)
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": DESCRIPTION_MAX}),
    )
    file = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, user: User, *args: Any, require_file: bool = True, **kwargs: Any) -> None:
        self.user = user
        self.require_file = require_file
        super().__init__(*args, **kwargs)

    def clean_description(self) -> str:
        return _fit(self.cleaned_data.get("description", ""), DESCRIPTION_MAX)

    def clean_file(self) -> StoredFile | None:
        raw = self.cleaned_data.get("file", "")
        if not raw:
            if self.require_file:
                raise forms.ValidationError(NEED_PDF)
            return None
        file = usable_file(self.user, raw, StoredFile.Purpose.REPORT)
        if file is None:
            raise forms.ValidationError(NEED_PDF)
        return file

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        start, end = data.get("period_start"), data.get("period_end")
        if start and end and end < start:
            self.add_error("period_end", PERIOD_ORDER)
        return data


class DecideForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decision",
        choices=[("accept", "Accept"), ("return", "Return to the program")],
        widget=forms.RadioSelect,
        initial="accept",
    )
    note = forms.CharField(
        label="Note to the program",
        help_text="Required when you return it.",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": NOTE_MAX}),
    )

    def clean_note(self) -> str:
        return _fit(self.cleaned_data.get("note", ""), NOTE_MAX)
