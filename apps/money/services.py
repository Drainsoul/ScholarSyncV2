"""Money writes. Audit data holds ids, codes, counts, statuses and amounts as strings only."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.awards.models import Award, ScholarTerm
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.money.models import Disbursement, DistributionSchedule
from apps.money.selectors import amount_for, eligible_terms, merit_confirmed, staff_schedule
from apps.programs.models import Program

ONE_LIVE_PAYOUT = "money_one_live_payout_per_term"


def _violates(exc: IntegrityError, constraint: str) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


def _locked_schedule(program: Program, schedule_id: int) -> DistributionSchedule:
    staff_schedule(program, schedule_id)  # Http404 outside the program
    return (
        DistributionSchedule.objects.select_for_update().select_related("term").get(pk=schedule_id)
    )


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
