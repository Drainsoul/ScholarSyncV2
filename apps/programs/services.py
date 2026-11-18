from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import record
from apps.core.permissions import require_office, require_settings_editor
from apps.core.text import counted

from .models import (
    AcademicTerm,
    BenefitTier,
    Program,
    ProgramMembership,
    RequiredDocument,
    School,
)
from .selectors import activation_problem, current_term, deactivation_counts, tier_in_use
from .terms import school_year_terms


@transaction.atomic
def add_membership(
    *,
    actor: User | None,
    user: User,
    program: Program,
    level: ProgramMembership.Level,
    request: HttpRequest | None = None,
) -> ProgramMembership:
    """Add a program-staff account to a program.

    `actor=None` means the command line or the demo; otherwise the actor must be a super admin.
    """
    _require_membership_editor(actor)
    if user.role != User.Role.STAFF:
        raise ValidationError("Only program staff accounts can be program members.")
    # Lock the account so two adds at once can't both pass the duplicate check.
    User.objects.select_for_update().get(pk=user.pk)
    if ProgramMembership.objects.filter(user=user, program=program).exists():
        name = user.full_name or user.email
        raise ValidationError(f"{name} is already in {program.name}.")
    membership = ProgramMembership.objects.create(user=user, program=program, level=level)
    record(
        actor=actor,
        action="membership.added",
        target=membership,
        program=program,
        data={"level": str(level)},
        request=request,
    )
    return membership


def _require_membership_editor(actor: User | None) -> None:
    if actor is not None and not (actor.is_super_admin and actor.is_active):
        raise PermissionDenied("Only the scholarship office can change program memberships.")


@transaction.atomic
def change_membership(
    *,
    actor: User,
    membership: ProgramMembership,
    level: ProgramMembership.Level,
    request: HttpRequest | None = None,
) -> ProgramMembership:
    """A new level; no event when it is the same."""
    _require_membership_editor(actor)
    locked = ProgramMembership.objects.select_for_update().get(pk=membership.pk)
    if locked.level == level:
        return locked
    previous = locked.level
    locked.level = level
    locked.save(update_fields=["level", "updated_at"])
    record(
        actor=actor,
        action="membership.changed",
        target=locked,
        program=locked.program,
        data={"from": str(previous), "to": str(level)},
        request=request,
    )
    return locked


@transaction.atomic
def remove_membership(
    *, actor: User, membership: ProgramMembership, request: HttpRequest | None = None
) -> None:
    """Take an account out of a program. The office still covers a program left without a head."""
    _require_membership_editor(actor)
    locked = ProgramMembership.objects.select_for_update().get(pk=membership.pk)
    record(
        actor=actor,
        action="membership.removed",
        target=locked,
        program=locked.program,
        data={"level": str(locked.level)},
        request=request,
    )
    locked.delete()


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


def _slug_taken(slug: str) -> bool:
    return Program.objects.filter(slug=slug).exists()


@transaction.atomic
def create_program(
    *, actor: User, slug: str, name: str, description: str, request: HttpRequest | None = None
) -> Program:
    """A new program, closed until the office opens it. The slug never changes afterwards."""
    require_office(actor)
    slug = slug.strip().lower()
    if _slug_taken(slug):
        raise ValidationError({"slug": SLUG_TAKEN})
    try:
        with transaction.atomic():
            program = Program.objects.create(
                slug=slug, name=name, description=description, is_active=False
            )
    except IntegrityError:  # a second post raced past the check
        raise ValidationError({"slug": SLUG_TAKEN}) from None
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
        if name == "allowed_school_types" and sorted(getattr(locked, name) or []) == sorted(
            value or []  # type: ignore[call-overload]
        ):
            continue  # the same types in another order
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


TIER_CODE_TAKEN = "That tier code is taken."
TIER_PAST_TERM = "Pick the current term or a later one."
TIER_NO_CURRENT = "Set a current term first: tier changes start from it."
TIER_IN_USE = "Records already use the {term} amounts for {tier}. Pick a later term."
TIER_CHANGED = "This tier changed while you were editing it. Check its amounts and try again."


def _tier_term(term: AcademicTerm) -> None:
    """Tier changes start now or later; the past stays as it was paid."""
    current = current_term()
    if current is None:
        raise ValidationError(TIER_NO_CURRENT)
    if term.sort_key < current.sort_key:
        raise ValidationError({"effective_from": TIER_PAST_TERM})


def _tier_audit(
    actor: User, program: Program, tier: BenefitTier, action: str, request: HttpRequest | None
) -> None:
    record(
        actor=actor,
        action=action,
        target=tier,
        program=program,
        data={
            "code": tier.code,
            "term": tier.effective_from_id,
            "base_amount": str(tier.base_amount),
            "merit_amount": str(tier.merit_amount),
        },
        request=request,
    )


@transaction.atomic
def add_tier(
    *,
    actor: User,
    program: Program,
    code: str,
    name: str,
    base_amount: Decimal,
    merit_amount: Decimal,
    effective_from: AcademicTerm,
    sort_order: int,
    request: HttpRequest | None = None,
) -> BenefitTier:
    require_settings_editor(actor, program)
    _tier_term(effective_from)
    Program.objects.select_for_update().get(pk=program.pk)
    if BenefitTier.objects.filter(program=program, code=code).exists():
        raise ValidationError({"code": TIER_CODE_TAKEN})
    tier = BenefitTier.objects.create(
        program=program,
        code=code,
        name=name,
        base_amount=base_amount,
        merit_amount=merit_amount,
        effective_from=effective_from,
        sort_order=sort_order,
    )
    _tier_audit(actor, program, tier, "tier.added", request)
    return tier


def _tier_row_for(
    program: Program, code: str, term: AcademicTerm
) -> tuple[BenefitTier, BenefitTier | None]:
    """The code's latest row (for its name and order) and its row for exactly `term`, if any.
    An unknown code is a 404."""
    rows = list(
        BenefitTier.objects.select_for_update()
        .filter(program=program, code=code)
        .order_by("effective_from__sort_key")
    )
    if not rows:
        raise Http404("No such tier.")
    same = next((row for row in rows if row.effective_from_id == term.pk), None)
    return rows[-1], same


def _write_tier_row(
    program: Program,
    code: str,
    term: AcademicTerm,
    *,
    base_amount: Decimal,
    merit_amount: Decimal,
    is_active: bool,
) -> BenefitTier:
    latest, same = _tier_row_for(program, code, term)
    if same is not None:
        if tier_in_use(same):
            raise ValidationError(TIER_IN_USE.format(term=term, tier=same.name))
        same.base_amount, same.merit_amount, same.is_active = base_amount, merit_amount, is_active
        same.save(update_fields=["base_amount", "merit_amount", "is_active", "updated_at"])
        return same
    try:
        with transaction.atomic():
            return BenefitTier.objects.create(
                program=program,
                code=code,
                name=latest.name,
                base_amount=base_amount,
                merit_amount=merit_amount,
                effective_from=term,
                is_active=is_active,
                sort_order=latest.sort_order,
            )
    except IntegrityError:  # another change wrote this term's row after we read
        raise ValidationError(TIER_CHANGED) from None


@transaction.atomic
def change_tier_amounts(
    *,
    actor: User,
    program: Program,
    code: str,
    base_amount: Decimal,
    merit_amount: Decimal,
    effective_from: AcademicTerm,
    request: HttpRequest | None = None,
) -> BenefitTier:
    """New amounts from `effective_from` on. Records already made keep the row they point to."""
    require_settings_editor(actor, program)
    _tier_term(effective_from)
    tier = _write_tier_row(
        program,
        code,
        effective_from,
        base_amount=base_amount,
        merit_amount=merit_amount,
        is_active=True,
    )
    _tier_audit(actor, program, tier, "tier.changed", request)
    return tier


@transaction.atomic
def stop_tier(
    *,
    actor: User,
    program: Program,
    code: str,
    effective_from: AcademicTerm,
    request: HttpRequest | None = None,
) -> BenefitTier:
    """The tier is no longer offered from `effective_from` (an inactive row ends it)."""
    require_settings_editor(actor, program)
    _tier_term(effective_from)
    latest, _ = _tier_row_for(program, code, effective_from)
    # The stopping row carries the amounts in force for that term (records priced from it keep
    # their amounts), not the newest row's, which may start later.
    in_force = (
        BenefitTier.objects.filter(
            program=program, code=code, effective_from__sort_key__lte=effective_from.sort_key
        )
        .order_by("-effective_from__sort_key")
        .first()
        or latest
    )
    tier = _write_tier_row(
        program,
        code,
        effective_from,
        base_amount=in_force.base_amount,
        merit_amount=in_force.merit_amount,
        is_active=False,
    )
    _tier_audit(actor, program, tier, "tier.stopped", request)
    return tier


DOCUMENT_CODE_TAKEN = "That document code is taken."
DOCUMENT_FIELDS = (
    "label",
    "help_text",
    "applies_to",
    "is_required",
    "accepted_types",
    "max_bytes",
    "sort_order",
)


def _document_audit(
    actor: User,
    program: Program,
    document: RequiredDocument,
    action: str,
    request: HttpRequest | None,
) -> None:
    record(
        actor=actor,
        action=action,
        target=document,
        program=program,
        data={"code": document.code},
        request=request,
    )


@transaction.atomic
def add_document(
    *,
    actor: User,
    program: Program,
    data: dict[str, object],
    request: HttpRequest | None = None,
) -> RequiredDocument:
    require_settings_editor(actor, program)
    Program.objects.select_for_update().get(pk=program.pk)
    code = str(data["code"])
    if RequiredDocument.objects.filter(program=program, code=code).exists():
        raise ValidationError({"code": DOCUMENT_CODE_TAKEN})
    document = RequiredDocument.objects.create(
        program=program, code=code, **{name: data[name] for name in DOCUMENT_FIELDS}
    )
    _document_audit(actor, program, document, "document.added", request)
    return document


@transaction.atomic
def update_document(
    *,
    actor: User,
    program: Program,
    document: RequiredDocument,
    data: dict[str, object],
    request: HttpRequest | None = None,
) -> RequiredDocument:
    """Everything but the code; no event when nothing changed."""
    require_settings_editor(actor, program)
    locked = RequiredDocument.objects.select_for_update().get(pk=document.pk, program=program)
    changed = [name for name in DOCUMENT_FIELDS if getattr(locked, name) != data[name]]
    if not changed:
        return locked
    asks_more = (not locked.is_required and bool(data["is_required"])) or (
        locked.applies_to != RequiredDocument.AppliesTo.BOTH
        and data["applies_to"] != locked.applies_to
    )
    for name in changed:
        setattr(locked, name, data[name])
    if asks_more:
        # Applications already sent don't answer to what they were never asked for.
        locked.required_since = timezone.now()
        changed.append("required_since")
    locked.save(update_fields=[*changed, "updated_at"])
    _document_audit(actor, program, locked, "document.updated", request)
    return locked


@transaction.atomic
def set_document_active(
    *,
    actor: User,
    program: Program,
    document: RequiredDocument,
    active: bool,
    request: HttpRequest | None = None,
) -> RequiredDocument:
    """Stop asking for a document, or ask again. It is never deleted: uploads point to it."""
    require_settings_editor(actor, program)
    locked = RequiredDocument.objects.select_for_update().get(pk=document.pk, program=program)
    if locked.is_active == active:
        return locked
    locked.is_active = active
    fields = ["is_active", "updated_at"]
    if active:
        locked.required_since = timezone.now()
        fields.append("required_since")
    locked.save(update_fields=fields)
    _document_audit(
        actor, program, locked, "document.restored" if active else "document.stopped", request
    )
    return locked


SCHOOL_TAKEN = "A school with this name already exists."


def _school_taken(name: str, school: School | None) -> bool:
    clash = School.objects.filter(name__iexact=name)
    if school is not None:
        clash = clash.exclude(pk=school.pk)
    return clash.exists()


@transaction.atomic
def save_school(
    *,
    actor: User,
    school: School | None,
    name: str,
    type: str,
    grading_scale: str,
    is_in_taguig: bool,
    request: HttpRequest | None = None,
) -> School:
    """Add a school (`school=None`) or edit one. Names are unique whatever their case."""
    require_office(actor)
    if _school_taken(name, school):
        raise ValidationError({"name": SCHOOL_TAKEN})
    fields = {
        "name": name,
        "type": type,
        "grading_scale": grading_scale,
        "is_in_taguig": is_in_taguig,
    }
    try:
        with transaction.atomic():
            if school is None:
                saved = School.objects.create(**fields)
                action = "school.added"
            else:
                saved = School.objects.select_for_update().get(pk=school.pk)
                changed = [f for f, value in fields.items() if getattr(saved, f) != value]
                if not changed:
                    return saved
                for field in changed:
                    setattr(saved, field, fields[field])
                saved.save(update_fields=[*changed, "updated_at"])
                action = "school.updated"
    except IntegrityError:  # a second post raced past the check
        raise ValidationError({"name": SCHOOL_TAKEN}) from None
    record(
        actor=actor,
        action=action,
        target=saved,
        data={"type": saved.type, "grading_scale": saved.grading_scale},
        request=request,
    )
    return saved
