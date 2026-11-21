from datetime import date
from typing import Any

from django import forms
from django.utils import timezone

from apps.core.text import normalize_newlines
from apps.programs.models import Program
from apps.workspace.models import ReplyTemplate, SupportRequest

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

    prefix_id = "reply"
    template = forms.IntegerField(required=False, widget=forms.HiddenInput)
    body = forms.CharField(
        label="Message",
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 8, "maxlength": 4000}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Both forms sit on one page: their own ids keep each label on its own field.
        kwargs.setdefault("auto_id", f"{self.prefix_id}-%s")
        super().__init__(*args, **kwargs)

    def clean_body(self) -> str:
        return normalize_newlines(self.cleaned_data["body"])


class EmailReplyForm(ReplyForm):
    """An answer by email: a one-line subject, then the message."""

    prefix_id = "email"
    subject = forms.CharField(label="Subject", max_length=150)
    field_order = ["template", "subject", "body"]

    def clean_subject(self) -> str:
        subject: str = self.cleaned_data["subject"]
        if "\r" in subject or "\n" in subject:
            raise forms.ValidationError("Enter the subject on one line.")
        return subject


class ReplyTemplateForm(forms.Form):
    """A reply template: where it applies, then the text it starts from."""

    title = forms.CharField(label="Title", max_length=80)
    topic = forms.ChoiceField(
        label="Topic", required=False, choices=[("", "Any topic"), *SupportRequest.Topic.choices]
    )
    program = forms.ModelChoiceField(
        label="Program",
        queryset=Program.objects.filter(is_active=True).order_by("name"),
        required=False,
        empty_label="Every program",
    )
    subject = forms.CharField(
        label="Email subject",
        max_length=150,
        required=False,
        help_text="Leave blank to use “Re: your message about …”.",
    )
    body = forms.CharField(
        label="Message",
        max_length=4000,
        help_text="{first_name} and {program} are filled in when the template is picked.",
        widget=forms.Textarea(attrs={"rows": 8, "maxlength": 4000}),
    )

    @classmethod
    def initial_for(cls, template: ReplyTemplate) -> dict[str, object]:
        return {
            "title": template.title,
            "topic": template.topic,
            "program": template.program_id,
            "subject": template.subject,
            "body": template.body,
        }

    def clean_body(self) -> str:
        return normalize_newlines(self.cleaned_data["body"])
