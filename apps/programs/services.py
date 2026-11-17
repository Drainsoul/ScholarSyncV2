from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.core.audit import record
from apps.core.permissions import require_office, require_settings_editor
from apps.core.text import counted

from .models import AcademicTerm, Program, ProgramMembership
from .selectors import activation_problem, current_term, deactivation_counts
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


# A transaction-scoped advisory lock: term changes run one at a time, even on an empty table
# (where row locks find nothing to lock), so a double post never rolls over twice or collides.
TERM_LOCK = 4_711_011


def _lock_terms() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [TERM_LOCK])


def _require_office(actor: User) -> None:
    if not (actor.is_super_admin and actor.is_active):
        raise PermissionDenied("Only the scholarship office can change school terms.")


@transaction.atomic
def add_school_year(*, actor: User, start: int) -> list[AcademicTerm]:
    """The three terms of school year `start` (the seed's dates), none current. Years go in
    order: only the year after the latest one, or any year when there are no terms yet."""
    _require_office(actor)
    _lock_terms()
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
    _lock_terms()
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


SLUG_TAKEN = "That slug is taken."


@transaction.atomic
def create_program(
    *, actor: User, slug: str, name: str, description: str, request: HttpRequest | None = None
) -> Program:
    """A new program, closed until the office opens it. The slug never changes afterwards."""
    require_office(actor)
    slug = slug.strip().lower()
    if Program.objects.filter(slug=slug).exists():
        raise ValidationError({"slug": SLUG_TAKEN})
    program = Program.objects.create(slug=slug, name=name, description=description, is_active=False)
    record(
        actor=actor,
        action="program.created",
        target=program,
        program=program,
        data={"slug": slug},
        request=request,
    )
    return program


@transaction.atomic
def update_program(
    *,
    actor: User,
    program: Program,
    name: str,
    description: str,
    request: HttpRequest | None = None,
) -> Program:
    require_office(actor)
    if (program.name, program.description) == (name, description):
        return program
    program.name, program.description = name, description
    program.save(update_fields=["name", "description", "updated_at"])
    record(
        actor=actor,
        action="program.updated",
        target=program,
        program=program,
        data={"slug": program.slug},
        request=request,
    )
    return program


@transaction.atomic
def set_program_active(
    *, actor: User, program: Program, active: bool, request: HttpRequest | None = None
) -> Program:
    """Open or close a program. Opening needs a tier and a document; closing waits for open work."""
    require_office(actor)
    locked = Program.objects.select_for_update().get(pk=program.pk)
    if locked.is_active == active:
        return locked
    if active:
        problem = activation_problem(locked, current_term())
        if problem is not None:
            raise ValidationError(problem)
    else:
        waiting, payouts = deactivation_counts(locked)
        if waiting or payouts:
            raise ValidationError(
                f"{locked.name} still has "
                f"{counted(waiting, 'waiting application', 'waiting applications')} and "
                f"{counted(payouts, 'payout', 'payouts')} in progress. Finish or reject them first."
            )
    locked.is_active = active
    locked.save(update_fields=["is_active", "updated_at"])
    record(
        actor=actor,
        action="program.activated" if active else "program.deactivated",
        target=locked,
        program=locked,
        data={"slug": locked.slug},
        request=request,
    )
    return locked


@transaction.atomic
def update_rules(
    *,
    actor: User,
    program: Program,
    data: dict[str, object],
    request: HttpRequest | None = None,
) -> list[str]:
    """Save a program's rules and window; return the changed field names (one event, or none).

    Submitted applications keep their frozen `match_snapshot`, so nothing is re-checked."""
    require_settings_editor(actor, program)
    locked = Program.objects.select_for_update().get(pk=program.pk)
    changed: list[str] = []
    schools = data.get("allowed_schools")
    for name, value in data.items():
        if name == "allowed_schools":
            continue
        if getattr(locked, name) != value:
            setattr(locked, name, value)
            changed.append(name)
    if changed:
        locked.save(update_fields=[*changed, "updated_at"])
    if schools is not None:
        wanted = {school.pk for school in schools}  # type: ignore[attr-defined]
        if set(locked.allowed_schools.values_list("pk", flat=True)) != wanted:
            locked.allowed_schools.set(wanted)
            changed.append("allowed_schools")
    if changed:
        record(
            actor=actor,
            action="program.rules_changed",
            target=locked,
            program=locked,
            data={"fields": sorted(changed)},
            request=request,
        )
    return changed
