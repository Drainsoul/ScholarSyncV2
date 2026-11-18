"""Money reads: amounts, schedules and what may be paid. Every staff lookup is program-scoped."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, Exists, OuterRef, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, QueryDict

from apps.accounts.models import User
from apps.awards.models import Award, ScholarTerm
from apps.core.templatetags.ui import peso
from apps.money.models import Budget, Disbursement, DistributionSchedule
from apps.programs.models import Program
from apps.programs.selectors import current_term

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Decimal("0")

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


def money_sum(field: str, condition: Q | None = None) -> Coalesce:
    """A Decimal sum that is 0, never None, over an empty set."""
    return Coalesce(Sum(field, filter=condition), Value(ZERO), output_field=MONEY)


def schedule_list(program: Program) -> QuerySet[DistributionSchedule]:
    """The program's schedules with a count (`n_<status>`) and a sum (`s_<status>`) of payouts
    per status."""
    totals: dict[str, Count | Coalesce] = {}
    for status in Disbursement.Status.values:
        condition = Q(disbursements__status=status)
        totals[f"n_{status}"] = Count("disbursements", filter=condition)
        totals[f"s_{status}"] = money_sum("disbursements__amount", condition)
    return schedules_for(program).annotate(**totals)


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


@dataclass(frozen=True)
class RowFilters:
    q: str = ""
    status: str = ""
    tier: str = ""


def parse_row_filters(params: QueryDict, program: Program) -> RowFilters:
    """Unknown values fall back to "all", never an error."""
    status = params.get("status", "")
    if status not in Disbursement.Status.values:
        status = ""
    tier = params.get("tier", "")
    if tier and not program.tiers.filter(code=tier).exists():
        tier = ""
    return RowFilters(
        q=params.get("q", "").replace("\x00", "").strip()[:200], status=status, tier=tier
    )


def schedule_rows(schedule: DistributionSchedule, filters: RowFilters) -> QuerySet[Disbursement]:
    rows = schedule.disbursements.select_related(
        "scholar_term__award__profile",
        "scholar_term__award__tier",
        "scholar_term__tier",
        "scholar_term__term",
    )
    if filters.status:
        rows = rows.filter(status=filters.status)
    if filters.tier:
        rows = rows.filter(
            Q(scholar_term__tier__code=filters.tier)
            | Q(scholar_term__tier__isnull=True, scholar_term__award__tier__code=filters.tier)
        )
    for word in filters.q.split():
        rows = rows.filter(
            Q(scholar_term__award__profile__first_name__icontains=word)
            | Q(scholar_term__award__profile__last_name__icontains=word)
        )
    return rows.order_by(
        "scholar_term__award__profile__last_name",
        "scholar_term__award__profile__first_name",
        "pk",
    )


def schedule_totals(schedule: DistributionSchedule) -> dict[str, tuple[int, Decimal]]:
    """Count and sum of the schedule's payouts per status."""
    values: dict[str, Count | Coalesce] = {}
    for status in Disbursement.Status.values:
        values[f"n_{status}"] = Count("pk", filter=Q(status=status))
        values[f"s_{status}"] = money_sum("amount", Q(status=status))
    found = schedule.disbursements.aggregate(**values)
    return {
        status: (found[f"n_{status}"], found[f"s_{status}"])
        for status in Disbursement.Status.values
    }


def schedule_disbursement(schedule: DistributionSchedule, pk: int) -> Disbursement:
    row = (
        schedule.disbursements.select_related("scholar_term__award__profile", "scholar_term__term")
        .filter(pk=pk)
        .first()
    )
    if row is None:
        raise Http404("This payout isn't in this schedule.")
    return row


@dataclass(frozen=True)
class BudgetSummary:
    year: int
    amount: Decimal | None  # None: no budget set for the year
    spent: Decimal
    committed: Decimal
    remaining: Decimal | None
    used_percent: int | None  # None with no budget or a zero budget
    over_by: Decimal | None


def budget_summary(program: Program, year: int) -> BudgetSummary:
    """A payout counts in the fiscal year of its schedule's distribution day (spec §4.7)."""
    found = Disbursement.objects.filter(
        schedule__program=program, schedule__distribution_date__year=year
    ).aggregate(
        spent=money_sum("amount", Q(status=Disbursement.Status.RELEASED)),
        committed=money_sum("amount", Q(status=Disbursement.Status.APPROVED)),
    )
    amount = (
        Budget.objects.filter(program=program, fiscal_year=year)
        .values_list("amount", flat=True)
        .first()
    )
    return _summary(year, amount, found["spent"], found["committed"])


def _summary(
    year: int, amount: Decimal | None, spent: Decimal, committed: Decimal
) -> BudgetSummary:
    remaining = amount - spent - committed if amount is not None else None
    used = int((spent + committed) * 100 // amount) if amount else None
    over_by = -remaining if remaining is not None and remaining < 0 else None
    return BudgetSummary(
        year=year,
        amount=amount,
        spent=spent,
        committed=committed,
        remaining=remaining,
        used_percent=used,
        over_by=over_by,
    )


def budget_summaries(programs: list[Program], year: int) -> dict[int, BudgetSummary]:
    """`budget_summary` for many programs in two queries, keyed by program id."""
    ids = [program.pk for program in programs]
    totals = {
        row["schedule__program_id"]: row
        for row in Disbursement.objects.filter(
            schedule__program_id__in=ids, schedule__distribution_date__year=year
        )
        .values("schedule__program_id")
        .annotate(
            spent=money_sum("amount", Q(status=Disbursement.Status.RELEASED)),
            committed=money_sum("amount", Q(status=Disbursement.Status.APPROVED)),
        )
        .order_by()
    }
    amounts = dict(
        Budget.objects.filter(program_id__in=ids, fiscal_year=year).values_list(
            "program_id", "amount"
        )
    )
    summaries: dict[int, BudgetSummary] = {}
    for pk in ids:
        row = totals.get(pk)
        spent: Decimal = row["spent"] if row else ZERO
        committed: Decimal = row["committed"] if row else ZERO
        summaries[pk] = _summary(year, amounts.get(pk), spent, committed)
    return summaries


def budget_figures(summary: BudgetSummary) -> list[dict[str, str]]:
    """The approved mockup's five tiles."""
    tone = ""
    if summary.amount is None or (not summary.amount and summary.over_by is None):
        # None, or a zero budget with nothing spent or approved.
        available = "No budget set"
    elif summary.over_by is not None:
        available = f"Over budget by {peso(summary.over_by)}"
        tone = "danger"
    else:
        available = peso(summary.remaining)
    return [
        {"label": f"Budget for {summary.year}", "value": peso(summary.amount)},
        {"label": "Released", "value": peso(summary.spent)},
        {"label": "Approved, not yet released", "value": peso(summary.committed)},
        {"label": "Available", "value": available, "tone": tone},
        {
            "label": "Budget used",
            "value": "—" if summary.used_percent is None else f"{summary.used_percent}%",
        },
    ]


def year_schedules(program: Program, year: int) -> QuerySet[DistributionSchedule]:
    return schedule_list(program).filter(distribution_date__year=year)


@dataclass(frozen=True)
class Payouts:
    times_claimed: int
    received: Decimal
    to_come: Decimal  # pending + approved in the current school year
    next_schedule: DistributionSchedule | None
    rows: list[Disbursement]  # newest term first


STUDENT_STATUS = {
    Disbursement.Status.PENDING: "Being prepared",
    Disbursement.Status.APPROVED: "Ready to claim",
    Disbursement.Status.RELEASED: "Received",
    Disbursement.Status.REJECTED: "Not paid",
}


def payouts_for_student(user: User, *, today: date) -> dict[int, Payouts]:
    """The student's own payouts per award, from published schedules only, in a fixed number
    of queries whatever the number of awards."""
    awards = dict(Award.objects.filter(profile__user=user).values_list("pk", "program_id"))
    active = set(
        Award.objects.filter(profile__user=user, status=Award.Status.ACTIVE).values_list(
            "pk", flat=True
        )
    )
    if not awards:
        return {}
    rows: dict[int, list[Disbursement]] = {pk: [] for pk in awards}
    for row in (
        Disbursement.objects.filter(scholar_term__award_id__in=awards, schedule__is_published=True)
        .select_related("schedule", "scholar_term__term")
        .order_by("-scholar_term__term__sort_key", "-schedule__distribution_date", "-pk")
    ):
        rows[row.scholar_term.award_id].append(row)
    recorded: dict[int, set[int]] = {pk: set() for pk in awards}
    for award_id, term_id in ScholarTerm.objects.filter(award_id__in=awards).values_list(
        "award_id", "term_id"
    ):
        recorded[award_id].add(term_id)
    upcoming = list(
        DistributionSchedule.objects.filter(
            program_id__in=set(awards.values()), is_published=True, distribution_date__gte=today
        )
        .select_related("term")
        .order_by("distribution_date", "pk")
    )
    term = current_term()
    year = term.school_year_start if term is not None else None
    found: dict[int, Payouts] = {}
    for pk, program_id in awards.items():
        mine = rows[pk]
        released = [row for row in mine if row.status == Disbursement.Status.RELEASED]
        to_come = sum(
            (
                row.amount
                for row in mine
                if pk in active  # an award on hold or ended has nothing to come
                and row.status in (Disbursement.Status.PENDING, Disbursement.Status.APPROVED)
                and row.scholar_term.term.school_year_start == year
            ),
            ZERO,
        )
        found[pk] = Payouts(
            times_claimed=len(released),
            received=sum((row.amount for row in released), ZERO),
            to_come=to_come,
            next_schedule=next(
                (
                    schedule
                    for schedule in upcoming
                    if schedule.program_id == program_id and schedule.term_id in recorded[pk]
                ),
                None,
            ),
            rows=mine,
        )
    return found


def released_in_year(program: Program, year: int) -> Decimal:
    """Released payouts whose schedule's distribution day falls in `year` (the budget year)."""
    found: Decimal = Disbursement.objects.filter(
        schedule__program=program,
        schedule__distribution_date__year=year,
        status=Disbursement.Status.RELEASED,
    ).aggregate(total=money_sum("amount"))["total"]
    return found


def payout_counts(program: Program) -> dict[str, int]:
    """Prepared and approved payouts in the program's published schedules."""
    return Disbursement.objects.filter(
        schedule__program=program, schedule__is_published=True
    ).aggregate(
        pending=Count("pk", filter=Q(status=Disbursement.Status.PENDING)),
        approved=Count("pk", filter=Q(status=Disbursement.Status.APPROVED)),
    )
