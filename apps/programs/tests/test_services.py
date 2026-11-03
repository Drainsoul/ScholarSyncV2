import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import ProgramMembership
from apps.programs.services import add_membership
from apps.programs.tests.factories import ProgramFactory


def test_add_membership_audits_with_the_program(db):
    actor = UserFactory.create(role=User.Role.SUPER_ADMIN)
    user = UserFactory.create(role=User.Role.STAFF)
    program = ProgramFactory.create()
    membership = add_membership(
        actor=actor, user=user, program=program, level=ProgramMembership.Level.HEAD
    )
    assert membership.level == "head"
    event = AuditEvent.objects.get(action="membership.added")
    assert event.program == program
    assert event.actor == actor
    assert event.target_id == str(membership.pk)
    assert event.data == {"level": "head"}


def test_students_cannot_be_members(db):
    with pytest.raises(ValidationError):
        add_membership(
            actor=None,
            user=UserFactory.create(),
            program=ProgramFactory.create(),
            level=ProgramMembership.Level.STAFF,
        )
    assert not ProgramMembership.objects.exists()
