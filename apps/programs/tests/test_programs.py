import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs import selectors
from apps.programs.tests.factories import MembershipFactory, ProgramFactory


def test_one_membership_per_user_and_program(db):
    membership = MembershipFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        MembershipFactory.create(user=membership.user, program=membership.program)


def test_programs_for_staff_lists_only_their_active_programs(db):
    staff = UserFactory.create(role=User.Role.STAFF)
    ceaa = ProgramFactory.create(slug="tcu-ceaa")
    ProgramFactory.create(slug="lani")
    closed = ProgramFactory.create(slug="closed", is_active=False)
    MembershipFactory.create(user=staff, program=ceaa)
    MembershipFactory.create(user=staff, program=closed)
    assert list(selectors.programs_for(staff)) == [ceaa]


def test_programs_for_super_admin_lists_every_active_program(db):
    admin = UserFactory.create(role=User.Role.SUPER_ADMIN)
    a = ProgramFactory.create(name="A")
    b = ProgramFactory.create(name="B")
    ProgramFactory.create(is_active=False)
    assert list(selectors.programs_for(admin)) == [a, b]


def test_programs_for_a_student_is_empty(db):
    student = UserFactory.create()
    program = ProgramFactory.create()
    MembershipFactory.create(user=student, program=program)
    assert list(selectors.programs_for(student)) == []


def test_membership_for_returns_membership_or_none(db):
    membership = MembershipFactory.create()
    assert selectors.membership_for(membership.user, membership.program) == membership
    other = ProgramFactory.create()
    assert selectors.membership_for(membership.user, other) is None
