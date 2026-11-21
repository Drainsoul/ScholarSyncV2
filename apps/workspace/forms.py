from datetime import date

from django import forms
from django.utils import timezone

from apps.core.text import normalize_newlines
from apps.programs.models import Program
from apps.workspace.models import SupportRequest

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


class TaskForm(forms.Form):
    title = forms.CharField(label="Task", max_length=200)
    due_on = forms.DateField(
        label="Due date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 2000}),
    )


class SupportForm(forms.Form):
    topic = forms.ChoiceField(label="What is it about?", choices=SupportRequest.Topic.choices)
    program = forms.ModelChoiceField(
        label="Program",
        queryset=Program.objects.filter(is_active=True).order_by("name"),
        required=False,
        empty_label="Not about one program",
    )
    message = forms.CharField(
        label="Your message",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 6, "maxlength": 2000}),
    )


class ReplyForm(forms.Form):
    """An answer in the app. `template` is the id of the picked template, if any (hidden)."""

    template = forms.IntegerField(required=False, widget=forms.HiddenInput)
    body = forms.CharField(
        label="Message",
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 8, "maxlength": 4000}),
    )

    def clean_body(self) -> str:
        return normalize_newlines(self.cleaned_data["body"])


class EmailReplyForm(ReplyForm):
    """An answer by email: a one-line subject, then the message."""

    subject = forms.CharField(label="Subject", max_length=150)
    field_order = ["template", "subject", "body"]

    def clean_subject(self) -> str:
        subject: str = self.cleaned_data["subject"]
        if "\r" in subject or "\n" in subject:
            raise forms.ValidationError("Enter the subject on one line.")
        return subject
