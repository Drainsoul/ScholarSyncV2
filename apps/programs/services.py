from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.core.audit import record

from .models import Program, ProgramMembership


@transaction.atomic
def add_membership(
    *,
    actor: User | None,
    user: User,
    program: Program,
    level: ProgramMembership.Level,
) -> ProgramMembership:
    if user.role != User.Role.STAFF:
        raise ValidationError("Only program staff accounts can be program members.")
    membership = ProgramMembership.objects.create(user=user, program=program, level=level)
    record(
        actor=actor,
        action="membership.added",
        target=membership,
        program=program,
        data={"level": str(level)},
    )
    return membership
