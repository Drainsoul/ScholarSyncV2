from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.core.audit import record

from .models import AcademicTerm, Program, ProgramMembership
from .terms import school_year_terms


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


SAME_TERM = "This is already the current term."
BACKWARD = "The current term can only move forward."


def _require_office(actor: User) -> None:
    if not (actor.is_super_admin and actor.is_active):
        raise PermissionDenied("Only the scholarship office can change school terms.")


@transaction.atomic
def add_school_year(*, actor: User, start: int) -> list[AcademicTerm]:
    """The three terms of school year `start` (the seed's dates), none current. Years go in
    order: only the year after the latest one, or any year when there are no terms yet."""
    _require_office(actor)
    latest = (
        AcademicTerm.objects.select_for_update()
        .order_by("-school_year_start")
        .values_list("school_year_start", flat=True)
        .first()
    )
    if latest is not None and start != latest + 1:
        raise ValidationError(f"Add school year {latest + 1}\u2013{latest + 2} next.")
    terms = [
        AcademicTerm.objects.create(
            school_year_start=spec.school_year_start,
            term=spec.term,
            starts_on=spec.starts_on,
            ends_on=spec.ends_on,
        )
        for spec in school_year_terms(date(start, 8, 1))
    ]
    record(actor=actor, action="term.year_added", target=terms[0], data={"start": start})
    return terms


@transaction.atomic
def set_current_term(*, actor: User, term: AcademicTerm) -> AcademicTerm | None:
    """Move the current-term flag forward to `term` and return the old current term.

    The old flag is cleared before the new one is set: `programs_one_current_term` allows one.
    The rollover is the caller's (`awards.services.start_term`)."""
    _require_office(actor)
    flagged = list(AcademicTerm.objects.select_for_update().filter(is_current=True))
    target = AcademicTerm.objects.select_for_update().get(pk=term.pk)
    old = flagged[0] if flagged else None
    if old is not None:
        if old.pk == target.pk:
            raise ValidationError(SAME_TERM)
        if target.sort_key < old.sort_key:
            raise ValidationError(BACKWARD)
        AcademicTerm.objects.filter(pk=old.pk).update(is_current=False)
    target.is_current = True
    target.save(update_fields=["is_current", "updated_at"])
    record(
        actor=actor,
        action="term.made_current",
        target=target,
        data={"from": old.pk if old is not None else None},
    )
    return old
