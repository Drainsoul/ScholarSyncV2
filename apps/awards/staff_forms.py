from typing import Any

from django import forms

from apps.applications.staff_forms import AcademicsForm
from apps.awards.models import Award
from apps.awards.services import AwardData, TermData
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import current_term, tiers_in_force


class AwardEditForm(forms.Form):
    student_number = forms.CharField(label="Student number", max_length=50, required=False)
    notes = forms.CharField(label="Notes", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    tier = forms.ModelChoiceField(
        label="Allowance tier",
        queryset=BenefitTier.objects.none(),
        empty_label=None,
        error_messages={"invalid_choice": "Choose one of this program's allowance tiers."},
    )

    def __init__(self, *args: Any, award: Award, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        term = current_term()
        pks = {tier.pk for tier in tiers_in_force(award.program, term)} if term else set()
        pks.add(award.tier_id)  # the award's own tier stays selectable even after a re-price
        tier_field = self.fields["tier"]
        assert isinstance(tier_field, forms.ModelChoiceField)
        tier_field.queryset = BenefitTier.objects.filter(pk__in=pks).order_by("sort_order", "name")


class StatusForm(forms.Form):
    to = forms.ChoiceField(choices=Award.Status.choices)
    reason = forms.CharField(
        label="Reason",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"max_length": "Keep the reason under 1,000 characters."},
        help_text="Staff see the reason on the scholar's record.",
    )


class TermRecordForm(AcademicsForm):
    """A staff term record: the M8b school-and-grades form, plus the term and the documents check.

    Editing a record drops the term field: the term never changes.
    """

    term = forms.ModelChoiceField(
        label="Term",
        queryset=AcademicTerm.objects.none(),
        empty_label=None,
        error_messages={"invalid_choice": "Choose a term this scholar has no record for yet."},
    )
    compliance_checked = forms.BooleanField(label="Renewal documents checked", required=False)

    def __init__(self, *args: Any, award: Award, editing: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if editing:
            del self.fields["term"]
            return
        current = current_term()
        term_field = self.fields["term"]
        assert isinstance(term_field, forms.ModelChoiceField)
        if current is not None:
            term_field.queryset = (
                AcademicTerm.objects.filter(sort_key__lte=current.sort_key)
                .exclude(pk__in=award.terms.values("term_id"))
                .order_by("-sort_key")
            )
        self.order_fields(["term"])

    def term_data(self, term: AcademicTerm) -> TermData:
        cleaned = self.cleaned_data
        return TermData(
            term=term,
            school=cleaned.get("school"),
            school_name=cleaned.get("school_name", ""),
            school_type=cleaned.get("school_type") or "",
            gwa_scale=cleaned.get("gwa_scale") or "",
            course=(cleaned.get("course") or "").strip(),
            year_level=cleaned.get("year_level"),
            gwa=cleaned.get("gwa"),
            units=cleaned.get("units"),
            compliance_checked=bool(cleaned.get("compliance_checked")),
        )


class MeritForm(forms.Form):
    merit = forms.ChoiceField(choices=[("yes", "Confirm merit"), ("no", "No merit")])


class NewScholarForm(AcademicsForm):
    """Add scholar: the award (start term, tier, student number, notes) and its first record."""

    term = forms.ModelChoiceField(
        label="Start term",
        queryset=AcademicTerm.objects.none(),
        empty_label=None,
        error_messages={"invalid_choice": "Choose the current term or an earlier one."},
    )
    tier = forms.ChoiceField(
        label="Allowance tier",
        error_messages={"invalid_choice": "Choose one of this program's allowance tiers."},
    )
    student_number = forms.CharField(label="Student number", max_length=50, required=False)
    notes = forms.CharField(label="Notes", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    compliance_checked = forms.BooleanField(label="Documents checked", required=False)

    def __init__(self, *args: Any, program: Program, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        current = current_term()
        term_field = self.fields["term"]
        tier_field = self.fields["tier"]
        assert isinstance(term_field, forms.ModelChoiceField)
        assert isinstance(tier_field, forms.ChoiceField)
        if current is not None:
            term_field.queryset = AcademicTerm.objects.filter(
                sort_key__lte=current.sort_key
            ).order_by("-sort_key")
            self.initial.setdefault("term", current)
            tier_field.choices = [
                (tier.code, tier.name) for tier in tiers_in_force(program, current)
            ]
        self.order_fields(["term", "tier", "student_number", "notes"])

    def award_data(self) -> AwardData:
        cleaned = self.cleaned_data
        return AwardData(
            tier_code=cleaned["tier"],
            student_number=(cleaned.get("student_number") or "").strip(),
            notes=(cleaned.get("notes") or "").strip(),
            record=TermData(
                term=cleaned["term"],
                school=cleaned.get("school"),
                school_name=cleaned.get("school_name", ""),
                school_type=cleaned.get("school_type") or "",
                gwa_scale=cleaned.get("gwa_scale") or "",
                course=(cleaned.get("course") or "").strip(),
                year_level=cleaned.get("year_level"),
                gwa=cleaned.get("gwa"),
                units=cleaned.get("units"),
                compliance_checked=bool(cleaned.get("compliance_checked")),
            ),
        )
