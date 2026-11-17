"""Money reads: amounts, schedules and what may be paid. Every staff lookup is program-scoped."""

from decimal import Decimal

from django.db.models import Exists, OuterRef, QuerySet
from django.http import Http404

from apps.awards.models import Award, ScholarTerm
from apps.money.models import Disbursement, DistributionSchedule
from apps.programs.models import Program

NOT_ACTIVE = "This scholar's award is {status}."
DOCUMENTS_UNCHECKED = "Check this scholar's documents for {term} first."


def merit_confirmed(record: ScholarTerm) -> bool:
    """Merit is paid only once staff confirmed it; a proposed merit is not."""
    return record.merit and record.merit_confirmed_by_id is not None


def amount_for(record: ScholarTerm) -> tuple[Decimal, bool]:
    """The term's amount and whether it pays merit. The tier is the row the term is paid at,
    else the award's; `merit_amount` is the full amount with merit, not an add-on."""
    tier = record.tier or record.award.tier
    if merit_confirmed(record) and tier.merit_amount > 0:
        return tier.merit_amount, True
    return tier.base_amount, False


def schedules_for(program: Program) -> QuerySet[DistributionSchedule]:
    return DistributionSchedule.objects.filter(program=program).select_related("term")


def staff_schedule(program: Program, pk: int) -> DistributionSchedule:
    schedule = schedules_for(program).filter(pk=pk).first()
    if schedule is None:
        raise Http404("No such schedule.")
    return schedule


def ineligible_reason(record: ScholarTerm) -> str:
    """Why this term can't be approved for payment now ("" when it can)."""
    award = record.award
    if award.status != Award.Status.ACTIVE:
        return NOT_ACTIVE.format(status=award.get_status_display().lower())
    if record.compliance != ScholarTerm.Compliance.COMPLETE:
        return DOCUMENTS_UNCHECKED.format(term=record.term)
    return ""


def eligible_terms(schedule: DistributionSchedule) -> QuerySet[ScholarTerm]:
    """Every term record of the schedule's program and term, with whether it already has a live
    payout in another schedule (`live_elsewhere`) or any row in this one (`in_schedule`)."""
    live = Disbursement.objects.filter(
        scholar_term=OuterRef("pk"), status__in=Disbursement.LIVE_STATUSES
    )
    return (
        ScholarTerm.objects.filter(award__program_id=schedule.program_id, term_id=schedule.term_id)
        .select_related("tier", "award__tier", "term")
        .annotate(
            live_elsewhere=Exists(live.exclude(schedule_id=schedule.pk)),
            in_schedule=Exists(
                Disbursement.objects.filter(scholar_term=OuterRef("pk"), schedule_id=schedule.pk)
            ),
        )
        .order_by("pk")
    )
