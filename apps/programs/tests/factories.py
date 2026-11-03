import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import Program, ProgramMembership


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
