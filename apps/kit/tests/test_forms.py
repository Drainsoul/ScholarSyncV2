from django.forms import ChoiceField

from apps.kit.forms import DecisionForm


def test_decision_tier_is_optional_unless_approving():
    assert DecisionForm().fields["tier"].required is False
    assert DecisionForm(data={"decision": "return"}).is_valid()
    assert DecisionForm(data={"decision": "reject", "tier": ""}).is_valid()


def test_approving_needs_a_tier():
    form = DecisionForm(data={"decision": "approve", "tier": ""})
    assert not form.is_valid()
    assert "tier" in form.errors
    assert DecisionForm(data={"decision": "approve", "tier": "honors"}).is_valid()


def test_decision_is_a_radio_choice_of_three():
    form = DecisionForm(data={"decision": "maybe"})
    assert not form.is_valid() and "decision" in form.errors
    field = DecisionForm().fields["decision"]
    assert isinstance(field, ChoiceField)
    assert all(field.valid_value(value) for value in ("approve", "return", "reject"))
