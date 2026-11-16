from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from django import forms

from apps.applications.models import Application
from apps.applications.review import (
    DECISION_REASON_TOO_LONG,
    DECLINE_REASON_TOO_LONG,
    MAX_DECISION_REASON,
    MAX_DECLINE_REASON,
    NEED_REJECT_REASON,
    NEED_RETURN_REASON,
)
from apps.programs.models import BenefitTier, Program, School
from apps.programs.selectors import tiers_in_force
from apps.students.forms import GWA_RANGES

APPROVE = "approve"
RETURN = "return"
REJECT = "reject"
NEED_TIER = "Choose the allowance tier."
NEED_SELECTION = "Select at least one application first."
NEED_ACTION = "Choose an action for the selected applications."
START_REVIEW = "start_review"


class DeclineForm(forms.Form):
    reason = forms.CharField(
        label="Reason",
        max_length=MAX_DECLINE_REASON,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={
            "required": "Say why you're declining this document.",
            "max_length": DECLINE_REASON_TOO_LONG,
        },
        help_text="The student reads this when you return the application.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # The dialog sits on a page whose decision form also has a "reason" field, so its ids
        # must differ or the label would point at the wrong textarea.
        kwargs.setdefault("auto_id", "decline_%s")
        super().__init__(*args, **kwargs)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decision",
        choices=[(APPROVE, "Approve"), (RETURN, "Return for changes"), (REJECT, "Don't approve")],
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose a decision.",
            "invalid_choice": "Choose a decision.",
        },
    )
    tier = forms.ModelChoiceField(
        label="Allowance tier",
        queryset=BenefitTier.objects.none(),
        required=False,
        empty_label="Choose a tier",
        error_messages={"invalid_choice": "Choose one of this program's allowance tiers."},
    )
    reason = forms.CharField(
        label="Reason or note",
        max_length=MAX_DECISION_REASON,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"max_length": DECISION_REASON_TOO_LONG},
        help_text=(
            "The student reads the reason for a return or a rejection. "
            "An approval note is for staff only."
        ),
    )

    def __init__(self, *args: object, program: Program, application: Application, **kwargs: object):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        in_force = tiers_in_force(program, application.term)
        tier_field = self.fields["tier"]
        assert isinstance(tier_field, forms.ModelChoiceField)
        tier_field.queryset = BenefitTier.objects.filter(
            pk__in=[tier.pk for tier in in_force]
        ).order_by("sort_order", "name")
        # Preselect the requested tier only while it is still offered.
        if application.requested_tier_id in {tier.pk for tier in in_force}:
            tier_field.initial = application.requested_tier_id

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        decision = cleaned.get("decision")
        reason = str(cleaned.get("reason") or "").strip()
        if decision == APPROVE and cleaned.get("tier") is None and "tier" not in self.errors:
            self.add_error("tier", NEED_TIER)
        elif decision == RETURN and not reason and "reason" not in self.errors:
            self.add_error("reason", NEED_RETURN_REASON)
        elif decision == REJECT and not reason and "reason" not in self.errors:
            self.add_error("reason", NEED_REJECT_REASON)
        return cleaned


class _IdsField(forms.MultipleChoiceField):
    """Application ids as ints; whether they exist is the service's business (it reports them)."""

    def valid_value(self, value: str) -> bool:
        return value.isascii() and value.isdigit() and len(value) <= 9

    def clean(self, value: object) -> list[int]:
        return [int(item) for item in super().clean(value)]


class BulkForm(forms.Form):
    ids = _IdsField(error_messages={"required": NEED_SELECTION, "invalid_choice": NEED_SELECTION})
    action = forms.ChoiceField(
        choices=[(START_REVIEW, "Start review"), (APPROVE, "Approve")],
        error_messages={"required": NEED_ACTION, "invalid_choice": NEED_ACTION},
    )


class AcademicsForm(forms.Form):
    """The student's school and grades, entered by staff onto an on-behalf draft."""

    school = forms.ModelChoiceField(
        queryset=School.objects.all(), required=False, empty_label="Not listed"
    )
    school_name = forms.CharField(label="School name", max_length=200, required=False)
    school_type = forms.ChoiceField(
        label="School type", choices=[("", "---------"), *School.Type.choices], required=False
    )
    gwa_scale = forms.ChoiceField(
        label="Grading scale", choices=[("", "---------"), *School.Scale.choices], required=False
    )
    course = forms.CharField(max_length=200, required=False)
    year_level = forms.IntegerField(label="Year level", min_value=1, max_value=10, required=False)
    gwa = forms.DecimalField(
        label="GWA", max_digits=5, decimal_places=2, required=False, localize=False
    )
    units = forms.IntegerField(min_value=0, max_value=1000, required=False)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        school = cleaned.get("school")
        name = (cleaned.get("school_name") or "").strip()
        cleaned["school_name"] = name
        if school is None and not name:
            if "school" not in self.errors:
                raise forms.ValidationError("Choose the student's school or type its name.")
        elif school is not None and name:
            raise forms.ValidationError("Choose a school from the list or type a name, not both.")

        if school is None and name:
            for field in ("school_type", "gwa_scale"):
                if not cleaned.get(field) and field not in self.errors:
                    self.add_error(field, "This field is required.")
        scale = school.grading_scale if school is not None else cleaned.get("gwa_scale")

        gwa: Decimal | None = cleaned.get("gwa")
        if gwa is not None and "gwa" not in self.errors:
            if not scale:
                if "gwa_scale" not in self.errors:
                    self.add_error("gwa_scale", "Choose the grading scale for the GWA.")
            else:
                low, high, message = GWA_RANGES[School.Scale(scale)]
                if not low <= gwa <= high:
                    self.add_error("gwa", message)
        return cleaned


class BehalfSubmitForm(forms.Form):
    """Submit on a student's behalf: the tier (radios when several are in force) and the reason
    for filing although a rule isn't met. Whether a reason is needed is the service's call.

    With one candidate there is no tier field and `cleaned_data["tier"]` is that tier; with none
    it is None (a resubmit keeps its tier; a draft is refused by the service).
    """

    override_reason = forms.CharField(
        label="Reason for filing anyway",
        max_length=MAX_DECISION_REASON,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"max_length": DECISION_REASON_TOO_LONG},
        help_text="Needed only when a rule isn't met.",
    )

    def __init__(self, *args: Any, candidates: Sequence[BenefitTier], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.candidates = list(candidates)
        if len(self.candidates) > 1:
            self.fields["tier"] = forms.ModelChoiceField(
                queryset=BenefitTier.objects.filter(pk__in=[t.pk for t in self.candidates]),
                widget=forms.RadioSelect,
                empty_label=None,
                label="Allowance tier",
                error_messages={
                    "required": NEED_TIER,
                    "invalid_choice": "Choose one of this program's allowance tiers.",
                },
            )
            self.order_fields(["tier", "override_reason"])

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if len(self.candidates) <= 1:
            cleaned["tier"] = self.candidates[0] if self.candidates else None
        return cleaned
