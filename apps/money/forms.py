"""Money forms. Views pass cleaned data to services; services re-check everything."""

from typing import Any

from django import forms

from apps.money.models import DistributionSchedule
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import current_term

MAX_NOTES = 1000


def schedule_terms() -> Any:
    """Terms up to the one after the current term (all of them with no current term)."""
    terms = AcademicTerm.objects.order_by("-sort_key")
    current = current_term()
    if current is None:
        return terms
    following = (
        AcademicTerm.objects.filter(sort_key__gt=current.sort_key).order_by("sort_key").first()
    )
    limit = following.sort_key if following is not None else current.sort_key
    return terms.filter(sort_key__lte=limit)


class ScheduleForm(forms.Form):
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.none(), label="Term")
    distribution_date = forms.DateField(
        label="Distribution day", widget=forms.DateInput(attrs={"type": "date"})
    )
    claim_location = forms.CharField(label="Claim location", max_length=200)
    frequency_label = forms.CharField(
        label="How often",
        max_length=80,
        required=False,
        help_text='For example "Once a semester". Scholars see it with the schedule.',
    )
    notes = forms.CharField(
        label="Notes for scholars",
        max_length=MAX_NOTES,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args: Any, program: Program, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        term = self.fields["term"]
        assert isinstance(term, forms.ModelChoiceField)
        term.queryset = schedule_terms()
        if not self.is_bound and "claim_location" not in self.initial:
            self.initial["claim_location"] = program.claim_location_default

    @staticmethod
    def initial_for(schedule: DistributionSchedule) -> dict[str, Any]:
        return {
            "term": schedule.term_id,
            "distribution_date": schedule.distribution_date,
            "claim_location": schedule.claim_location,
            "frequency_label": schedule.frequency_label,
            "notes": schedule.notes,
        }
