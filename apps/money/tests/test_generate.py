from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.core.models import AuditEvent
from apps.money import selectors, services
from apps.money.models import Disbursement, DistributionSchedule
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.programs.models import BenefitTier, Program, ProgramMembership
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)

pytestmark = pytest.mark.django_db

COMPLETE = ScholarTerm.Compliance.COMPLETE


def _tier(program: Program) -> BenefitTier:
    return BenefitTierFactory.create(
        program=program, base_amount=Decimal("5000.00"), merit_amount=Decimal("10000.00")
    )


def _record(schedule: DistributionSchedule, **kwargs: Any) -> ScholarTerm:
    tier = kwargs.pop("tier", None) or _tier(schedule.program)
    award = AwardFactory.create(
        source_application__program=schedule.program,
        tier=tier,
        status=kwargs.pop("status", Award.Status.ACTIVE),
    )
    values: dict[str, Any] = {"compliance": COMPLETE, "tier": tier}
    values.update(kwargs)
    return ScholarTermFactory.create(award=award, term=schedule.term, **values)


def _staff(program: Program) -> User:
    return MembershipFactory.create(program=program, level=ProgramMembership.Level.STAFF).user


def _generate(schedule: DistributionSchedule) -> services.GenerateResult:
    return services.generate(
        actor=_staff(schedule.program), program=schedule.program, schedule_id=schedule.pk
    )


def test_amount_is_base_without_confirmed_merit() -> None:
    record = _record(ScheduleFactory.create())
    assert selectors.amount_for(record) == (Decimal("5000.00"), False)


def test_amount_is_merit_amount_when_confirmed() -> None:
    record = _record(ScheduleFactory.create(), merit=True, merit_confirmed_by=UserFactory.create())
    assert selectors.merit_confirmed(record)
    assert selectors.amount_for(record) == (Decimal("10000.00"), True)


def test_proposed_merit_is_paid_the_base_amount() -> None:
    record = _record(ScheduleFactory.create(), merit=True)
    assert not selectors.merit_confirmed(record)
    assert selectors.amount_for(record) == (Decimal("5000.00"), False)


def test_zero_merit_amount_pays_base() -> None:
    schedule = ScheduleFactory.create()
    tier = BenefitTierFactory.create(program=schedule.program, merit_amount=Decimal("0"))
    record = _record(schedule, tier=tier, merit=True, merit_confirmed_by=UserFactory.create())
    assert selectors.amount_for(record) == (Decimal("5000.00"), False)


def test_amount_falls_back_to_the_award_tier() -> None:
    record = _record(ScheduleFactory.create())
    record.tier = None
    record.save()
    assert selectors.amount_for(record) == (Decimal("5000.00"), False)


def test_generate_creates_one_pending_row_per_eligible_term() -> None:
    schedule = ScheduleFactory.create()
    records = [_record(schedule) for _ in range(3)]
    result = _generate(schedule)
    assert result.created == 3
    rows = Disbursement.objects.filter(schedule=schedule)
    assert {row.scholar_term_id for row in rows} == {r.pk for r in records}
    assert all(row.amount == Decimal("5000.00") and row.status == "pending" for row in rows)
    event = AuditEvent.objects.get(action="disbursements.generated")
    assert event.data["schedule"] == schedule.pk
    assert event.data["created"] == 3


def test_generate_skips_and_counts() -> None:
    schedule = ScheduleFactory.create()
    _record(schedule)
    _record(schedule, status=Award.Status.SUSPENDED)
    _record(schedule, compliance=ScholarTerm.Compliance.INCOMPLETE)
    elsewhere = _record(schedule)
    other = ScheduleFactory.create(program=schedule.program, term=schedule.term)
    DisbursementFactory.create(scholar_term=elsewhere, schedule=other)
    ScholarTermFactory.create(  # another term of the same program: not counted
        award=AwardFactory.create(source_application__program=schedule.program),
        term=AcademicTermFactory.create(),
        compliance=COMPLETE,
    )
    _record(ScheduleFactory.create())  # another program: not counted
    result = _generate(schedule)
    assert (result.created, result.not_active, result.incomplete, result.elsewhere) == (1, 1, 1, 1)


def test_generate_again_refreshes_pending_only() -> None:
    schedule = ScheduleFactory.create()
    record = _record(schedule, merit=True)
    approved = _record(schedule, merit=True)
    _generate(schedule)
    Disbursement.objects.filter(scholar_term=approved).update(status="approved")
    confirmer = UserFactory.create()
    ScholarTerm.objects.filter(pk__in=[record.pk, approved.pk]).update(merit_confirmed_by=confirmer)
    result = _generate(schedule)
    assert (result.created, result.refreshed) == (0, 1)
    pending = Disbursement.objects.get(scholar_term=record)
    assert (pending.amount, pending.merit) == (Decimal("10000.00"), True)
    assert Disbursement.objects.get(scholar_term=approved).amount == Decimal("5000.00")
    assert Disbursement.objects.count() == 2


def test_generate_reports_merit_to_confirm() -> None:
    schedule = ScheduleFactory.create()
    _record(schedule, merit=True)
    _record(schedule)
    assert _generate(schedule).merit_to_confirm == 1


def test_generate_survives_a_concurrent_live_row() -> None:
    schedule = ScheduleFactory.create()
    raced = _record(schedule)
    calm = _record(schedule)
    other = ScheduleFactory.create(program=schedule.program, term=schedule.term)
    real = selectors.eligible_terms

    def stale(target: DistributionSchedule) -> Any:
        rows = list(real(target))  # selected before the other schedule's row lands
        DisbursementFactory.create(scholar_term=raced, schedule=other)
        return rows

    with mock.patch.object(services, "eligible_terms", side_effect=stale):
        result = _generate(schedule)
    assert (result.created, result.elsewhere) == (1, 1)
    assert Disbursement.objects.get(schedule=schedule).scholar_term_id == calm.pk


def test_generate_other_program_schedule_is_404() -> None:
    schedule = ScheduleFactory.create()
    program = ProgramFactory.create()
    with pytest.raises(Http404):
        services.generate(actor=_staff(program), program=program, schedule_id=schedule.pk)


def test_generate_needs_program_staff() -> None:
    schedule = ScheduleFactory.create()
    with pytest.raises(PermissionDenied):
        services.generate(
            actor=UserFactory.create(), program=schedule.program, schedule_id=schedule.pk
        )


def test_ineligible_reason() -> None:
    schedule = ScheduleFactory.create()
    assert selectors.ineligible_reason(_record(schedule)) == ""
    held = _record(schedule, status=Award.Status.SUSPENDED)
    assert selectors.ineligible_reason(held) == "This scholar's award is suspended."
    record = _record(schedule, compliance=ScholarTerm.Compliance.INCOMPLETE)
    assert selectors.ineligible_reason(record) == (
        f"Check this scholar's documents for {schedule.term} first."
    )


def test_generate_query_count(django_assert_max_num_queries: Any) -> None:
    schedule = ScheduleFactory.create()
    tier = _tier(schedule.program)
    for _ in range(50):
        _record(schedule, tier=tier)
    actor = _staff(schedule.program)
    with django_assert_max_num_queries(15):
        result = services.generate(actor=actor, program=schedule.program, schedule_id=schedule.pk)
    assert result.created == 50
