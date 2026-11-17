from datetime import date
from decimal import Decimal

import factory

from apps.accounts.tests.factories import UserFactory
from apps.awards.tests.factories import ScholarTermFactory
from apps.money.models import Budget, Disbursement, DistributionSchedule
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory


class ScheduleFactory(factory.django.DjangoModelFactory[DistributionSchedule]):
    class Meta:
        model = DistributionSchedule

    program = factory.declarations.SubFactory(ProgramFactory)
    term = factory.declarations.SubFactory(AcademicTermFactory)
    distribution_date = date(2026, 9, 15)
    claim_location = "Taguig City University Gymnasium"
    is_published = True
    created_by = factory.declarations.SubFactory(UserFactory, verified=True)


class DisbursementFactory(factory.django.DjangoModelFactory[Disbursement]):
    """Keeps the schedule in the scholar term's program and term."""

    class Meta:
        model = Disbursement

    scholar_term = factory.declarations.SubFactory(ScholarTermFactory)
    schedule = factory.declarations.SubFactory(
        ScheduleFactory,
        program=factory.declarations.SelfAttribute("..scholar_term.award.program"),
        term=factory.declarations.SelfAttribute("..scholar_term.term"),
    )
    amount = Decimal("5000.00")
    status = Disbursement.Status.PENDING


class BudgetFactory(factory.django.DjangoModelFactory[Budget]):
    class Meta:
        model = Budget

    program = factory.declarations.SubFactory(ProgramFactory)
    fiscal_year = 2026
    amount = Decimal("1000000.00")
    updated_by = factory.declarations.SubFactory(UserFactory, verified=True)
