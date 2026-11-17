"""Test builders shared by the money tests."""

from datetime import date
from decimal import Decimal
from typing import Any

from apps.accounts.models import User
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.money.models import Disbursement, DistributionSchedule
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import BenefitTierFactory, MembershipFactory


def head_of(program: Program) -> User:
    return MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user


def staff_of(program: Program) -> User:
    return MembershipFactory.create(program=program, level=ProgramMembership.Level.STAFF).user


def payout(
    schedule: DistributionSchedule | None = None,
    *,
    status: str = Disbursement.Status.PENDING,
    award_status: str = Award.Status.ACTIVE,
    compliance: str = ScholarTerm.Compliance.COMPLETE,
    amount: Decimal = Decimal("5000.00"),
    **schedule_kwargs: Any,
) -> Disbursement:
    """A payout of an eligible scholar term in `schedule` (a new published one by default)."""
    if schedule is None:
        schedule = ScheduleFactory.create(**schedule_kwargs)
    tier = BenefitTierFactory.create(
        program=schedule.program,
        base_amount=Decimal("5000.00"),
        merit_amount=Decimal("10000.00"),
    )
    award = AwardFactory.create(
        source_application__program=schedule.program, tier=tier, status=award_status
    )
    record = ScholarTermFactory.create(
        award=award, term=schedule.term, tier=tier, compliance=compliance
    )
    return DisbursementFactory.create(
        scholar_term=record, schedule=schedule, status=status, amount=amount
    )


DAY = date(2027, 3, 14)
