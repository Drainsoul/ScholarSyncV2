"""Money writes. Audit data holds ids, codes, counts, statuses and amounts as strings only."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.awards.models import Award, ScholarTerm
from apps.core import audit
from apps.core.permissions import require_program_head, require_program_staff
from apps.core.templatetags.ui import peso
from apps.core.transitions import assert_transition
from apps.money.models import Budget, Disbursement, DistributionSchedule
from apps.money.selectors import (
    NOT_ACTIVE,
    amount_for,
    eligible_terms,
    ineligible_reason,
    merit_confirmed,
    staff_schedule,
)
from apps.programs.models import AcademicTerm, Program
from apps.workspace.emails import enqueue

ONE_LIVE_PAYOUT = "money_one_live_payout_per_term"
MAX_REASON = 1000
NEED_REASON = "Give a reason."
REASON_TOO_LONG = "Keep the reason under 1,000 characters."
NOT_PUBLISHED = "Publish the schedule first."
TOO_EARLY = "Release after the distribution day, {date}."
PAID_ELSEWHERE = "This scholar already has a payout for {term}."
NOT_IN_SCHEDULE = "This payout isn't in this schedule."
BULK_TOO_MANY = "Choose at most 100 payouts at a time."
MAX_BULK = 100
MAX_ALL = 500


def long_date(day: date) -> str:
    """14 March 2027 (no leading zero)."""
    return f"{day.day} {day:%B %Y}"


def _violates(exc: IntegrityError, constraint: str) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


def _locked_schedule(program: Program, schedule_id: int) -> DistributionSchedule:
    schedule = (
        DistributionSchedule.objects.select_for_update(of=("self",))
        .select_related("term", "program")
        .filter(pk=schedule_id, program=program)
        .first()
    )
    if schedule is None:
        raise Http404("No such schedule.")
    return schedule


FROZEN = "This schedule has approved payouts, so its term and date are fixed."
TERM_FIXED = "This schedule has payouts, so its term is fixed."
STAYS_PUBLISHED = "This schedule has approved payouts, so it stays published."
MONEY_MOVED = (Disbursement.Status.APPROVED, Disbursement.Status.RELEASED)


@dataclass(frozen=True)
class ScheduleData:
    term: AcademicTerm
    distribution_date: date
    claim_location: str
    frequency_label: str
    notes: str


@transaction.atomic
def save_schedule(
    *,
    actor: User,
    program: Program,
    schedule_id: int | None,
    data: ScheduleData,
    request: HttpRequest | None = None,
) -> DistributionSchedule:
    """Create or edit a schedule. Once money moves its term and date are fixed (the budget year
    follows the date), and once it has any payout its term is."""
    require_program_staff(actor, program)
    values: dict[str, object] = {
        "term": data.term,
        "distribution_date": data.distribution_date,
        "claim_location": data.claim_location.strip()[:200],
        "frequency_label": data.frequency_label.strip()[:80],
        "notes": data.notes.strip(),
    }
    if schedule_id is None:
        schedule = DistributionSchedule.objects.create(program=program, created_by=actor, **values)
        audit.record(
            actor=actor,
            action="schedule.created",
            target=schedule,
            program=program,
            request=request,
            data={"term": data.term.pk},
        )
        return schedule
    schedule = _locked_schedule(program, schedule_id)
    changed = [field for field, value in values.items() if getattr(schedule, field) != value]
    if not changed:
        return schedule
    rows = schedule.disbursements.all()
    if {"term", "distribution_date"} & set(changed) and rows.filter(
        status__in=MONEY_MOVED
    ).exists():
        raise ValidationError(FROZEN)
    if "term" in changed and rows.exists():
        raise ValidationError(TERM_FIXED)
    for field in changed:
        setattr(schedule, field, values[field])
    schedule.save(update_fields=[*changed, "updated_at"])
    audit.record(
        actor=actor,
        action="schedule.updated",
        target=schedule,
        program=program,
        request=request,
        data={"fields": changed},
    )
    return schedule


@transaction.atomic
def set_published(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    published: bool,
    request: HttpRequest | None = None,
) -> DistributionSchedule:
    """Students see published schedules only. One with approved payouts stays published."""
    require_program_staff(actor, program)
    schedule = _locked_schedule(program, schedule_id)
    if schedule.is_published == published:
        return schedule
    if not published and schedule.disbursements.filter(status__in=MONEY_MOVED).exists():
        raise ValidationError(STAYS_PUBLISHED)
    schedule.is_published = published
    schedule.save(update_fields=["is_published", "updated_at"])
    audit.record(
        actor=actor,
        action="schedule.published" if published else "schedule.unpublished",
        target=schedule,
        program=program,
        request=request,
    )
    return schedule


@dataclass(frozen=True)
class GenerateResult:
    created: int
    refreshed: int
    not_active: int
    incomplete: int
    elsewhere: int
    merit_to_confirm: int


@transaction.atomic
def generate(
    *, actor: User, program: Program, schedule_id: int, request: HttpRequest | None = None
) -> GenerateResult:
    """Prepare a payout for every eligible term of the schedule, and recalculate its prepared
    rows. Nothing is deleted; approved, rejected and released rows never change."""
    require_program_staff(actor, program)
    schedule = _locked_schedule(program, schedule_id)
    new: list[Disbursement] = []
    not_active = incomplete = elsewhere = 0
    for record in eligible_terms(schedule):
        if record.in_schedule:  # type: ignore[attr-defined]
            continue
        if record.live_elsewhere:  # type: ignore[attr-defined]
            elsewhere += 1
        elif record.award.status != Award.Status.ACTIVE:
            not_active += 1
        elif record.compliance != ScholarTerm.Compliance.COMPLETE:
            incomplete += 1
        else:
            amount, merit = amount_for(record)
            new.append(
                Disbursement(scholar_term=record, schedule=schedule, amount=amount, merit=merit)
            )
    created = len(new)
    try:
        with transaction.atomic():  # a savepoint, so the outer transaction survives the error
            Disbursement.objects.bulk_create(new)
    except IntegrityError as exc:
        if not _violates(exc, ONE_LIVE_PAYOUT):
            raise
        created = 0
        for row in new:  # a live row landed elsewhere since the read: go one by one
            try:
                with transaction.atomic():
                    row.pk = None
                    row.save()
            except IntegrityError as row_exc:
                if not _violates(row_exc, ONE_LIVE_PAYOUT):
                    raise
                elsewhere += 1
            else:
                created += 1
    pending = list(
        schedule.disbursements.filter(status=Disbursement.Status.PENDING).select_related(
            "scholar_term__tier", "scholar_term__award__tier"
        )
    )
    changed = []
    merit_to_confirm = 0
    now = timezone.now()
    created_ids = {row.pk for row in new if row.pk is not None}
    for row in pending:
        record = row.scholar_term
        if record.merit and not merit_confirmed(record):
            merit_to_confirm += 1
        amount, merit = amount_for(record)
        if (row.amount, row.merit) != (amount, merit) and row.pk not in created_ids:
            row.amount, row.merit, row.updated_at = amount, merit, now
            changed.append(row)
    Disbursement.objects.bulk_update(changed, ["amount", "merit", "updated_at"])
    result = GenerateResult(
        created=created,
        refreshed=len(changed),
        not_active=not_active,
        incomplete=incomplete,
        elsewhere=elsewhere,
        merit_to_confirm=merit_to_confirm,
    )
    audit.record(
        actor=actor,
        action="disbursements.generated",
        target=schedule,
        program=program,
        request=request,
        data={
            "schedule": schedule.pk,
            "created": result.created,
            "refreshed": result.refreshed,
            "not_active": not_active,
            "incomplete": incomplete,
            "elsewhere": elsewhere,
        },
    )
    return result


def _locked_row(
    program: Program, schedule_id: int, disbursement_id: int
) -> tuple[DistributionSchedule, Disbursement]:
    """The schedule, then the payout, both locked. Http404 when either is outside the URL's."""
    schedule = _locked_schedule(program, schedule_id)
    row = (
        Disbursement.objects.select_for_update(of=("self",))
        .select_related(
            "scholar_term__award__profile__user", "scholar_term__term", "scholar_term__tier"
        )
        .filter(pk=disbursement_id, schedule=schedule)
        .first()
    )
    if row is None:
        raise Http404(NOT_IN_SCHEDULE)
    row.schedule = schedule
    return schedule, row


def allowance_email(
    row: Disbursement, kind: Literal["allowance_approved", "allowance_released"]
) -> None:
    """Tell the scholar; a profile nobody has claimed gets no email. Never the reason."""
    profile = row.scholar_term.award.profile
    if profile.user is None:
        return
    schedule = row.schedule
    context = {
        "full_name": profile.full_name,
        "program_name": schedule.program.name,
        "term_label": str(schedule.term),
        "amount": peso(row.amount),
        "scholarships_url": settings.SITE_URL + reverse("scholarships:list"),
    }
    if kind == "allowance_approved":
        context["claim_date"] = long_date(schedule.distribution_date)
        context["claim_location"] = schedule.claim_location
    enqueue(to=profile.user.email, kind=kind, context=context)


_ACTIONS = {
    Disbursement.Status.APPROVED: "disbursement.approved",
    Disbursement.Status.REJECTED: "disbursement.rejected",
    Disbursement.Status.RELEASED: "disbursement.released",
    Disbursement.Status.PENDING: "disbursement.reverted",
}


def _record(
    actor: User,
    program: Program,
    row: Disbursement,
    previous: str,
    request: HttpRequest | None,
) -> None:
    audit.record(
        actor=actor,
        action=_ACTIONS[Disbursement.Status(row.status)],
        target=row,
        program=program,
        request=request,
        data={"from": previous, "to": row.status, "amount": str(row.amount)},
    )


@transaction.atomic
def approve(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    disbursement_id: int,
    request: HttpRequest | None = None,
) -> Disbursement:
    """A head approves a prepared payout; the scholar is told when and where to claim."""
    require_program_head(actor, program)
    schedule, row = _locked_row(program, schedule_id, disbursement_id)
    assert_transition(row, Disbursement.Status.APPROVED)
    if not schedule.is_published:
        raise ValidationError(NOT_PUBLISHED)
    reason = ineligible_reason(row.scholar_term)
    if reason:
        raise ValidationError(reason)
    previous = row.status
    row.status = Disbursement.Status.APPROVED
    row.approved_by = actor
    row.approved_at = timezone.now()
    row.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _record(actor, program, row, previous, request)
    allowance_email(row, "allowance_approved")
    return row


@transaction.atomic
def reject(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    disbursement_id: int,
    reason: str,
    request: HttpRequest | None = None,
) -> Disbursement:
    """A head refuses a prepared payout. The reason is free text: it stays out of audit data."""
    require_program_head(actor, program)
    _, row = _locked_row(program, schedule_id, disbursement_id)
    assert_transition(row, Disbursement.Status.REJECTED)
    reason = reason.strip()
    if not reason:
        raise ValidationError(NEED_REASON)
    if len(reason) > MAX_REASON:
        raise ValidationError(REASON_TOO_LONG)
    previous = row.status
    row.status = Disbursement.Status.REJECTED
    row.decision_reason = reason
    row.save(update_fields=["status", "decision_reason", "updated_at"])
    _record(actor, program, row, previous, request)
    return row


@transaction.atomic
def release(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    disbursement_id: int,
    request: HttpRequest | None = None,
) -> Disbursement:
    """A head records that an approved payout was claimed, on or after the distribution day."""
    require_program_head(actor, program)
    schedule, row = _locked_row(program, schedule_id, disbursement_id)
    assert_transition(row, Disbursement.Status.RELEASED)
    award = row.scholar_term.award
    if award.status != Award.Status.ACTIVE:
        raise ValidationError(NOT_ACTIVE.format(status=award.get_status_display().lower()))
    if timezone.localdate() < schedule.distribution_date:
        raise ValidationError(TOO_EARLY.format(date=long_date(schedule.distribution_date)))
    previous = row.status
    row.status = Disbursement.Status.RELEASED
    row.released_at = timezone.now()
    row.save(update_fields=["status", "released_at", "updated_at"])
    _record(actor, program, row, previous, request)
    allowance_email(row, "allowance_released")
    return row


@transaction.atomic
def revert(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    disbursement_id: int,
    request: HttpRequest | None = None,
) -> Disbursement:
    """Back to prepared, from approved (before release) or rejected."""
    require_program_head(actor, program)
    schedule, row = _locked_row(program, schedule_id, disbursement_id)
    assert_transition(row, Disbursement.Status.PENDING)
    previous = row.status
    row.status = Disbursement.Status.PENDING
    row.approved_by = None
    row.approved_at = None
    row.decision_reason = ""
    fields = ["status", "approved_by", "approved_at", "decision_reason", "updated_at"]
    try:
        with transaction.atomic():  # a savepoint, so the outer transaction survives the error
            row.save(update_fields=fields)
    except IntegrityError as exc:
        if not _violates(exc, ONE_LIVE_PAYOUT):
            raise
        raise ValidationError(PAID_ELSEWHERE.format(term=schedule.term)) from None
    _record(actor, program, row, previous, request)
    return row


@dataclass(frozen=True)
class BulkResult:
    done: int
    skipped: list[tuple[str, str]]
    remaining: int


def bulk(
    *,
    actor: User,
    program: Program,
    schedule_id: int,
    action: Literal["approve", "release"],
    ids: list[int] | None,
    request: HttpRequest | None = None,
) -> BulkResult:
    """Approve or release the chosen payouts, or (ids=None) up to MAX_ALL in the action's source
    status. Each row runs in its own transaction, in pk order; refused rows are reported."""
    require_program_head(actor, program)  # a PermissionDenied is not a per-row skip
    schedule = staff_schedule(program, schedule_id)
    # Refusals that hold for every row are said once, not once per row (each row re-checks).
    if action == "approve" and not schedule.is_published:
        raise ValidationError(NOT_PUBLISHED)
    if action == "release" and timezone.localdate() < schedule.distribution_date:
        raise ValidationError(TOO_EARLY.format(date=long_date(schedule.distribution_date)))
    source = Disbursement.Status.PENDING if action == "approve" else Disbursement.Status.APPROVED
    rows = Disbursement.objects.filter(schedule_id=schedule_id).select_related(
        "scholar_term__award__profile"
    )
    if ids is None:
        found = list(rows.filter(status=source).order_by("pk")[:MAX_ALL])
        wanted = [row.pk for row in found]
    else:
        wanted = list(dict.fromkeys(ids))
        if len(wanted) > MAX_BULK:
            raise ValidationError(BULK_TOO_MANY)
        found = list(rows.filter(pk__in=wanted).order_by("pk"))
    act = approve if action == "approve" else release
    skipped: list[tuple[str, str]] = []
    done = 0
    for row in found:
        try:
            act(
                actor=actor,
                program=program,
                schedule_id=schedule_id,
                disbursement_id=row.pk,
                request=request,
            )
        except (ValidationError, Http404) as error:  # InvalidTransition is a ValidationError
            reason = " ".join(error.messages) if isinstance(error, ValidationError) else str(error)
            skipped.append((row.scholar_term.award.profile.full_name, reason))
        else:
            done += 1
    found_ids = {row.pk for row in found}
    skipped.extend(("", NOT_IN_SCHEDULE) for pk in wanted if pk not in found_ids)
    # Only rows past the cap are "more to go": refused rows stay in the source status on purpose.
    remaining = 0
    if ids is None and len(found) >= MAX_ALL:
        remaining = rows.filter(status=source, pk__gt=found[-1].pk).count()
    return BulkResult(done=done, skipped=skipped, remaining=remaining)


@transaction.atomic
def set_budget(
    *,
    actor: User,
    program: Program,
    year: int,
    amount: Decimal,
    request: HttpRequest | None = None,
) -> Budget:
    """The program's budget for a fiscal year (heads; the view asks for the password again)."""
    require_program_head(actor, program)
    if amount < 0:
        raise ValidationError("The budget can't be negative.")
    budget, _ = Budget.objects.select_for_update().update_or_create(
        program=program,
        fiscal_year=year,
        defaults={"amount": amount, "updated_by": actor},
    )
    audit.record(
        actor=actor,
        action="budget.set",
        target=budget,
        program=program,
        request=request,
        data={"year": str(year), "amount": str(budget.amount)},
    )
    return budget
