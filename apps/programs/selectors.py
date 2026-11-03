from django.db.models import QuerySet

from apps.accounts.models import User
from apps.programs.models import Program, ProgramMembership


def programs_for(user: User) -> QuerySet[Program]:
    """Active programs this user may work in: all for the office, their own for staff."""
    active = Program.objects.filter(is_active=True)
    if user.is_super_admin:
        return active
    if user.is_program_staff:
        return active.filter(memberships__user=user)
    return Program.objects.none()


def membership_for(user: User, program: Program) -> ProgramMembership | None:
    return ProgramMembership.objects.filter(user=user, program=program).first()
