import pytest

from apps.applications.models import Application
from apps.applications.review import NEED_REJECT_REASON, NEED_RETURN_REASON
from apps.applications.staff_forms import DecisionForm, DeclineForm
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.tests.factories import BenefitTierFactory, ProgramFactory

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


def test_decline_form_ids_do_not_clash_with_the_decision_form() -> None:
    from apps.applications.staff_forms import DeclineForm

    assert DeclineForm()["reason"].id_for_label == "decline_reason"
