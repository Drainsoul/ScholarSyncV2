import pytest

from apps.applications.models import Application
from apps.applications.review import NEED_REJECT_REASON, NEED_RETURN_REASON
from apps.applications.staff_forms import AcademicsForm, DecisionForm, DeclineForm
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.models import School
from apps.programs.tests.factories import BenefitTierFactory, ProgramFactory, SchoolFactory

pytestmark = pytest.mark.django_db


def _application(**kwargs: object) -> Application:
    program = ProgramFactory.create()
    return ApplicationFactory.create(
        program=program, status=Application.Status.UNDER_REVIEW, **kwargs
    )


def _form(application: Application, **data: object) -> DecisionForm:
    return DecisionForm(data or None, program=application.program, application=application)


def test_decision_form_needs_reason_for_return_and_reject() -> None:
    application = _application()
    form = _form(application, decision="return", reason="  ")
    assert not form.is_valid()
    assert form.errors["reason"] == [NEED_RETURN_REASON]
    form = _form(application, decision="reject", reason="")
    assert not form.is_valid()
    assert form.errors["reason"] == [NEED_REJECT_REASON]
    assert _form(application, decision="return", reason="Blurry scan.").is_valid()
    assert _form(application, decision="reject", reason="Out of area.").is_valid()


def test_decision_form_approve_needs_a_tier_but_not_a_reason() -> None:
    application = _application()
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    assert not _form(application, decision="approve").is_valid()
    form = _form(application, decision="approve", tier=tier.pk)
    assert form.is_valid()
    assert form.cleaned_data["tier"] == tier


def test_decision_form_tier_choices_are_tiers_in_force() -> None:
    application = _application()
    live = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    BenefitTierFactory.create(
        program=application.program, effective_from=application.term, is_active=False
    )
    other = BenefitTierFactory.create(effective_from=application.term)  # another program
    form = _form(application)
    assert list(form.fields["tier"].queryset) == [live]  # type: ignore[attr-defined]
    bad = _form(application, decision="approve", tier=other.pk)
    assert not bad.is_valid()
    assert "tier" in bad.errors


def test_decision_form_preselects_requested_tier_only_when_in_force() -> None:
    application = _application()
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    application.requested_tier = tier
    assert _form(application).fields["tier"].initial == tier.pk
    tier.is_active = False
    tier.save()
    assert _form(application).fields["tier"].initial is None


def test_decline_form_reason_is_required_and_capped() -> None:
    assert not DeclineForm({"reason": " "}).is_valid()
    assert not DeclineForm({"reason": "x" * 501}).is_valid()
    assert DeclineForm({"reason": "x" * 500}).is_valid()


def test_decline_form_too_long_uses_the_service_sentence() -> None:
    form = DeclineForm({"reason": "x" * 501})
    assert not form.is_valid()
    assert form.errors["reason"] == ["Keep the reason under 500 characters."]


def test_decision_form_too_long_uses_the_service_sentence() -> None:
    application = _application()
    form = _form(application, decision="return", reason="x" * 1001)
    assert not form.is_valid()
    assert form.errors["reason"] == ["Keep the reason under 1,000 characters."]
    assert _form(application, decision="return", reason="x" * 1000).is_valid()


def test_decision_form_reason_help_text() -> None:
    assert DecisionForm.base_fields["reason"].help_text == (
        "The student reads the reason for a return or a rejection. "
        "An approval note is for staff only."
    )


def test_decline_form_ids_do_not_clash_with_the_decision_form() -> None:
    from apps.applications.staff_forms import DeclineForm

    assert DeclineForm()["reason"].id_for_label == "decline_reason"


def _academics(**data: object) -> AcademicsForm:
    base = {"course": "BS Biology", "year_level": "2", "gwa": "88.5", "units": "21"}
    return AcademicsForm({**base, **data})


def test_academics_form_needs_a_school() -> None:
    form = _academics()
    assert not form.is_valid()
    assert form.non_field_errors() == ["Choose the student's school or type its name."]


def test_academics_form_not_both() -> None:
    school = SchoolFactory.create()
    form = _academics(school=school.pk, school_name="Elsewhere")
    assert not form.is_valid()
    assert form.non_field_errors() == ["Choose a school from the list or type a name, not both."]


def test_academics_form_typed_school_needs_type_and_scale() -> None:
    form = _academics(school_name="Taguig Tech")
    assert not form.is_valid()
    assert "school_type" in form.errors
    assert "gwa_scale" in form.errors
    form = _academics(school_name="Taguig Tech", school_type="private", gwa_scale="percent")
    assert form.is_valid(), form.errors


def test_academics_form_gwa_range_by_scale() -> None:
    form = _academics(
        school_name="Taguig Tech", school_type="private", gwa_scale="one_to_five", gwa="95"
    )
    assert not form.is_valid()
    assert form.errors["gwa"] == ["Enter a GWA from 1.00 to 5.00."]


def test_academics_form_listed_school_uses_its_scale() -> None:
    school = SchoolFactory.create(grading_scale=School.Scale.ONE_TO_FIVE)
    assert not _academics(school=school.pk, gwa="95").is_valid()
    form = _academics(school=school.pk, gwa="1.75")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["school"] == school
