from typing import Any

import pytest
from django.db import IntegrityError, transaction

from apps.awards.tests.factories import ScholarTermFactory
from apps.core.transitions import InvalidTransition, assert_transition
from apps.money.models import Disbursement
from apps.money.tests.factories import BudgetFactory, DisbursementFactory, ScheduleFactory

pytestmark = pytest.mark.django_db


def _constraint(exc: IntegrityError) -> str:
    return str(getattr(getattr(exc.__cause__, "diag", None), "constraint_name", ""))


def test_second_live_payout_for_a_term_is_refused() -> None:
    first = DisbursementFactory.create()
    other = ScheduleFactory.create(program=first.schedule.program, term=first.schedule.term)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        DisbursementFactory.create(scholar_term=first.scholar_term, schedule=other)
    assert _constraint(exc.value) == "money_one_live_payout_per_term"


def test_a_rejected_row_does_not_block_a_new_payout() -> None:
    first = DisbursementFactory.create(status=Disbursement.Status.REJECTED)
    other = ScheduleFactory.create(program=first.schedule.program, term=first.schedule.term)
    DisbursementFactory.create(scholar_term=first.scholar_term, schedule=other)
    assert Disbursement.objects.count() == 2


def test_same_schedule_twice_is_refused() -> None:
    first = DisbursementFactory.create(status=Disbursement.Status.REJECTED)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        DisbursementFactory.create(scholar_term=first.scholar_term, schedule=first.schedule)
    assert _constraint(exc.value) == "money_one_payout_per_schedule"


@pytest.mark.parametrize(
    ("field", "value", "name"),
    [("amount", "-1.00", "money_amount_gte_0"), ("status", "paid", "money_status_valid")],
)
def test_negative_amount_and_unknown_status_are_refused(field: str, value: str, name: str) -> None:
    row = DisbursementFactory.create()
    setattr(row, field, value)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        row.save()
    assert _constraint(exc.value) == name


ALLOWED = {
    ("pending", "approved"),
    ("pending", "rejected"),
    ("approved", "released"),
    ("approved", "pending"),
    ("rejected", "pending"),
}


@pytest.mark.parametrize("start", ["pending", "approved", "rejected", "released"])
@pytest.mark.parametrize("to", ["pending", "approved", "rejected", "released"])
def test_transitions_match_the_spec(start: str, to: str) -> None:
    row = Disbursement(status=start)
    if (start, to) in ALLOWED:
        assert_transition(row, to)
    else:
        with pytest.raises(InvalidTransition):
            assert_transition(row, to)


def test_pending_is_labelled_prepared() -> None:
    assert Disbursement.Status.PENDING.label == "Prepared"


def test_one_budget_per_program_and_year() -> None:
    budget = BudgetFactory.create()
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        BudgetFactory.create(program=budget.program, fiscal_year=budget.fiscal_year)
    assert _constraint(exc.value) == "money_one_budget_per_year"


def test_factory_keeps_schedule_and_term_together(db: Any) -> None:
    row = DisbursementFactory.create()
    assert row.schedule.term_id == row.scholar_term.term_id
    assert row.schedule.program_id == row.scholar_term.award.program_id
    assert ScholarTermFactory._meta.model is type(row.scholar_term)
