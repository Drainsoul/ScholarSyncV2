from datetime import date

import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import AcademicTerm, Program, ProgramMembership, School
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
