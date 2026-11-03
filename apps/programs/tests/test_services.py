import pytest
from django.core.exceptions import PermissionDenied, ValidationError

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


@pytest.mark.parametrize(
    "actor_fields",
    [
        {"role": User.Role.STAFF},
        {"role": User.Role.STUDENT},
        {"role": User.Role.SUPER_ADMIN, "is_active": False},
    ],
)
def test_only_an_active_super_admin_adds_members(db, actor_fields):
    with pytest.raises(PermissionDenied):
        add_membership(
            actor=UserFactory.create(**actor_fields),
            user=UserFactory.create(role=User.Role.STAFF),
            program=ProgramFactory.create(),
            level=ProgramMembership.Level.STAFF,
        )
    assert not ProgramMembership.objects.exists()
    assert not AuditEvent.objects.filter(action="membership.added").exists()
