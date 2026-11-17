from typing import Any

from django import forms

from apps.accounts.models import User
from apps.core.text import normalize_newlines
from apps.files.models import StoredFile
from apps.files.selectors import usable_file

from .services import NEED_PDF, PERIOD_ORDER

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ReportForm(forms.Form):
    """Send a report, or fix and send a returned one (the file is optional then)."""

    title = forms.CharField(label="Title", max_length=200)
    period_start = forms.DateField(label="Period from", widget=DATE)
    period_end = forms.DateField(label="Period to", widget=DATE)
    description = forms.CharField(
        label="Description",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
    )
    file = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, user: User, *args: Any, require_file: bool = True, **kwargs: Any) -> None:
        self.user = user
        self.require_file = require_file
        super().__init__(*args, **kwargs)

    def clean_description(self) -> str:
        return normalize_newlines(self.cleaned_data.get("description", ""))

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
