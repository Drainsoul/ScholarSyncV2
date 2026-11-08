from datetime import date
from decimal import Decimal

import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import (
    AcademicTerm,
    BenefitTier,
    Program,
    ProgramMembership,
    RequiredDocument,
    School,
)
from apps.programs.terms import school_year_terms


class ProgramFactory(factory.django.DjangoModelFactory[Program]):
    class Meta:
        model = Program

    slug = factory.declarations.Sequence(lambda n: f"program-{n}")
    name = factory.declarations.Sequence(lambda n: f"Program {n}")
    description = ""
    is_active = True


class MembershipFactory(factory.django.DjangoModelFactory[ProgramMembership]):
    class Meta:
        model = ProgramMembership

    user = factory.declarations.SubFactory(UserFactory, role=User.Role.STAFF)
    program = factory.declarations.SubFactory(ProgramFactory)
    level = ProgramMembership.Level.STAFF


class SchoolFactory(factory.django.DjangoModelFactory[School]):
    class Meta:
        model = School

    name = factory.declarations.Sequence(lambda n: f"School {n}")
    type = School.Type.PRIVATE
    grading_scale = School.Scale.PERCENT
    is_in_taguig = False


class AcademicTermFactory(factory.django.DjangoModelFactory[AcademicTerm]):
    class Meta:
        model = AcademicTerm

    school_year_start = factory.declarations.Sequence(lambda n: 2000 + n)
    term = AcademicTerm.Term.FIRST
    starts_on = factory.declarations.LazyAttribute(
        lambda o: school_year_terms(date(o.school_year_start, 8, 1))[o.term - 1].starts_on
    )
    ends_on = factory.declarations.LazyAttribute(
        lambda o: school_year_terms(date(o.school_year_start, 8, 1))[o.term - 1].ends_on
    )
    is_current = False


class BenefitTierFactory(factory.django.DjangoModelFactory[BenefitTier]):
    class Meta:
        model = BenefitTier

    program = factory.declarations.SubFactory(ProgramFactory)
    code = factory.declarations.Sequence(lambda n: f"tier-{n}")
    name = factory.declarations.Sequence(lambda n: f"Tier {n}")
    base_amount = Decimal("5000.00")
    merit_amount = Decimal("0.00")
    effective_from = factory.declarations.SubFactory(AcademicTermFactory)
    is_active = True
    sort_order = 0


class RequiredDocumentFactory(factory.django.DjangoModelFactory[RequiredDocument]):
    class Meta:
        model = RequiredDocument

    program = factory.declarations.SubFactory(ProgramFactory)
    code = factory.declarations.Sequence(lambda n: f"doc-{n}")
    label = factory.declarations.Sequence(lambda n: f"Document {n}")
    help_text = ""
    applies_to = RequiredDocument.AppliesTo.BOTH
    is_required = True
    sort_order = 0
