from django.core.exceptions import PermissionDenied, ValidationError
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
    """Add a program-staff account to a program.

    `actor=None` means the command line or the demo; otherwise the actor must be a super admin.
    """
    if actor is not None and not (actor.is_super_admin and actor.is_active):
        raise PermissionDenied("Only the scholarship office can change program memberships.")
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
