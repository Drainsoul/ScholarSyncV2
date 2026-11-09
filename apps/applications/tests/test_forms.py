import pytest

from apps.applications.forms import DECLARATION_LABEL, DocumentForm, SubmitForm
from apps.programs.tests.factories import AcademicTermFactory, BenefitTierFactory, ProgramFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tiers():
    term = AcademicTermFactory.create(school_year_start=2026, is_current=True)
    program = ProgramFactory.create()
    return [
        BenefitTierFactory.create(program=program, effective_from=term, code="full", name="Full"),
        BenefitTierFactory.create(program=program, effective_from=term, code="half", name="Half"),
    ]


def test_declaration_label_is_exact():
    form = SubmitForm(candidates=[])
    assert form.fields["declaration"].label == DECLARATION_LABEL
    assert DECLARATION_LABEL == (
        "I declare that the information and documents I have given are true and complete, "
        "and I agree that the scholarship office may check them."
    )


def test_declaration_is_required(tiers):
    form = SubmitForm({"tier": tiers[0].pk}, candidates=tiers)
    assert not form.is_valid()
    assert "declaration" in form.errors


def test_several_tiers_offer_radios_and_require_a_choice(tiers):
    form = SubmitForm({"declaration": "on"}, candidates=tiers)
    assert "tier" in form.fields
    queryset = form.fields["tier"].queryset  # type: ignore[attr-defined]
    assert [choice.pk for choice in queryset] == [t.pk for t in tiers]
    assert not form.is_valid()
    assert "tier" in form.errors


def test_several_tiers_yield_the_chosen_tier(tiers):
    form = SubmitForm({"tier": tiers[1].pk, "declaration": "on"}, candidates=tiers)
    assert form.is_valid()
    assert form.cleaned_data["tier"] == tiers[1]


def test_tier_outside_the_candidates_is_refused(tiers):
    other = BenefitTierFactory.create(code="x")
    form = SubmitForm({"tier": other.pk, "declaration": "on"}, candidates=tiers)
    assert not form.is_valid()
    assert "tier" in form.errors


def test_one_tier_has_no_field_and_yields_it(tiers):
    form = SubmitForm({"declaration": "on", "tier": tiers[1].pk}, candidates=tiers[:1])
    assert "tier" not in form.fields
    assert form.is_valid()
    assert form.cleaned_data["tier"] == tiers[0]


def test_no_tier_yields_none():
    form = SubmitForm({"declaration": "on"}, candidates=[])
    assert form.is_valid()
    assert form.cleaned_data["tier"] is None


def test_document_form_passes_the_raw_id():
    form = DocumentForm({"file": "not-a-uuid"})
    assert form.is_valid()
    assert form.cleaned_data["file"] == "not-a-uuid"
    assert not DocumentForm({"file": ""}).is_valid()
