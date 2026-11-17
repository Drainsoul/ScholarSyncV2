from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD
from apps.core.models import AuditEvent
from apps.money import selectors, services
from apps.money.models import Budget, Disbursement
from apps.money.tests.builders import head_of, payout, staff_of
from apps.money.tests.factories import BudgetFactory, ScheduleFactory
from apps.programs.models import Program
from apps.programs.tests.factories import ProgramFactory

pytestmark = pytest.mark.django_db

APPROVED = Disbursement.Status.APPROVED
RELEASED = Disbursement.Status.RELEASED


def _program_with_rows() -> Program:
    in_2026 = payout(distribution_date=date(2026, 9, 15), status=RELEASED)
    program = in_2026.schedule.program
    payout(in_2026.schedule, status=APPROVED, amount=Decimal("3000.00"))
    payout(in_2026.schedule, status=Disbursement.Status.PENDING)
    payout(in_2026.schedule, status=Disbursement.Status.REJECTED)
    in_2027 = ScheduleFactory.create(program=program, distribution_date=date(2027, 1, 20))
    payout(in_2027, status=RELEASED, amount=Decimal("7000.00"))
    return program


def test_summary_sums_released_and_approved_by_distribution_year() -> None:
    program = _program_with_rows()
    BudgetFactory.create(program=program, fiscal_year=2026, amount=Decimal("100000.00"))
    summary = selectors.budget_summary(program, 2026)
    assert (summary.spent, summary.committed) == (Decimal("5000.00"), Decimal("3000.00"))
    assert summary.remaining == Decimal("92000.00")
    assert summary.used_percent == 8
    later = selectors.budget_summary(program, 2027)
    assert (later.spent, later.committed, later.amount) == (Decimal("7000.00"), Decimal("0"), None)


def test_empty_and_zero_budget() -> None:
    program = ProgramFactory.create()
    empty = selectors.budget_summary(program, 2026)
    assert (empty.amount, empty.spent, empty.committed) == (None, Decimal("0"), Decimal("0"))
    assert (empty.remaining, empty.used_percent, empty.over_by) == (None, None, None)
    row = payout(distribution_date=date(2026, 9, 15), status=APPROVED)
    BudgetFactory.create(program=row.schedule.program, fiscal_year=2026, amount=Decimal("0"))
    zero = selectors.budget_summary(row.schedule.program, 2026)
    assert zero.over_by == Decimal("5000.00")
    assert zero.used_percent is None


def test_used_percent_rounds_down() -> None:
    row = payout(distribution_date=date(2026, 9, 15), status=RELEASED, amount=Decimal("333333.33"))
    BudgetFactory.create(program=row.schedule.program, amount=Decimal("1000000.00"))
    assert selectors.budget_summary(row.schedule.program, 2026).used_percent == 33


def test_moving_an_unapproved_schedule_moves_its_year() -> None:
    row = payout(distribution_date=date(2026, 12, 30))
    schedule = row.schedule
    program = schedule.program
    Disbursement.objects.filter(pk=row.pk).update(status=APPROVED)
    assert selectors.budget_summary(program, 2026).committed == Decimal("5000.00")
    Disbursement.objects.filter(pk=row.pk).update(status=Disbursement.Status.PENDING)
    services.save_schedule(
        actor=staff_of(program),
        program=program,
        schedule_id=schedule.pk,
        data=services.ScheduleData(
            term=schedule.term,
            distribution_date=date(2027, 1, 2),
            claim_location=schedule.claim_location,
            frequency_label=schedule.frequency_label,
            notes=schedule.notes,
        ),
    )
    Disbursement.objects.filter(pk=row.pk).update(status=APPROVED)
    assert selectors.budget_summary(program, 2026).committed == Decimal("0")
    assert selectors.budget_summary(program, 2027).committed == Decimal("5000.00")


def test_set_budget_upserts_and_audits() -> None:
    program = ProgramFactory.create()
    head = head_of(program)
    services.set_budget(actor=head, program=program, year=2026, amount=Decimal("500.00"))
    services.set_budget(actor=head, program=program, year=2026, amount=Decimal("750.00"))
    assert Budget.objects.get().amount == Decimal("750.00")
    events = AuditEvent.objects.filter(action="budget.set").order_by("pk")
    assert [event.data for event in events] == [
        {"year": "2026", "amount": "500.00"},
        {"year": "2026", "amount": "750.00"},
    ]


def _budget_url(program: Program, name: str = "budget") -> str:
    return reverse(f"money:{name}", args=[program.slug])


def _login(client: Any, user: User) -> Any:
    assert client.login(email=user.email, password=DEFAULT_PASSWORD)
    return client


def test_budget_page_tiles(client: Any, time_machine: Any) -> None:
    time_machine.move_to(date(2026, 10, 1))
    row = payout(distribution_date=date(2026, 9, 15), status=APPROVED)
    program = row.schedule.program
    BudgetFactory.create(program=program, fiscal_year=2026, amount=Decimal("0"))
    client.force_login(staff_of(program))
    html = client.get(_budget_url(program)).content.decode()
    for label in (
        "Budget for 2026",
        "Released",
        "Approved, not yet released",
        "Available",
        "Budget used",
    ):
        assert label in html
    assert "Over budget by ₱5,000.00" in html
    assert "Set budget" not in html
    html = client.get(_budget_url(program) + "?year=2027").content.decode()
    assert "No budget set" in html
    assert "Budget for 2027" in html
    assert "Budget for 2026" in client.get(_budget_url(program) + "?year=abc").content.decode()


def test_head_sees_set_budget(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(head_of(program))
    assert "Set budget" in client.get(_budget_url(program)).content.decode()


def test_budget_edit_needs_password_then_saves(client: Any) -> None:
    program = ProgramFactory.create()
    c = _login(client, head_of(program))
    url = _budget_url(program, "budget-edit")
    response = c.post(url, {"year": "2026", "amount": "1000000.00"})
    assert response.url.startswith(reverse("account_reauthenticate"))
    response = c.post(response.url, {"password": DEFAULT_PASSWORD})
    assert response.url == _budget_url(program) + "?year=2026"
    assert Budget.objects.get(program=program).amount == Decimal("1000000.00")


def test_budget_edit_refuses_staff_and_negative(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(staff_of(program))
    assert client.get(_budget_url(program, "budget-edit")).status_code == 403
    client.logout()
    c = _login(client, head_of(program))
    c.post(reverse("account_reauthenticate"), {"password": DEFAULT_PASSWORD})
    response = c.post(_budget_url(program, "budget-edit"), {"year": "2026", "amount": "-1"})
    assert response.status_code == 400
    assert not Budget.objects.exists()


def test_budget_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    program = _program_with_rows()
    client.force_login(staff_of(program))
    with django_assert_max_num_queries(12):
        assert client.get(_budget_url(program) + "?year=2026").status_code == 200


def test_budget_form_posts_to_a_url_without_a_query(client: Any) -> None:
    """allauth replays a POST after the password page only when its path is the whole `next`;
    a form posting to `?year=…` would come back as a GET and lose the amount."""
    program = ProgramFactory.create()
    client.force_login(head_of(program))
    html = client.get(_budget_url(program, "budget-edit") + "?year=2026").content.decode()
    assert f'action="{_budget_url(program, "budget-edit")}"' in html
