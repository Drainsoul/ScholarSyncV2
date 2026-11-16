from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import Http404, QueryDict

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.matching.eligibility import window_reason
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import application_term, tiers_in_force, window_state
from apps.students.models import StudentProfile

# A renewal in one of these states settles the term: nothing more is due.
SETTLING_STATUSES = frozenset(
    {*Application.OPEN_STATUSES, Application.Status.APPROVED, Application.Status.REJECTED}
)


def holds_award(profile: StudentProfile, program: Program) -> bool:
    """An active award, or one on hold: either way the student holds the scholarship."""
    return Award.objects.filter(
        profile=profile, program=program, status__in=Award.HELD_STATUSES
    ).exists()


def other_active_awards(profile: StudentProfile, program: Program) -> list[Award]:
    return list(
        Award.objects.filter(profile=profile, status=Award.Status.ACTIVE)
        .exclude(program=program)
        .select_related("program")
        .order_by("program__name", "pk")
    )


class RenewalStatus(StrEnum):
    DUE = "due"
    OPEN = "open"
    RENEWED = "renewed"
    REJECTED = "rejected"
    SUMMER = "summer"
    NO_TERM = "no_term"
    NOT_ACTIVE = "not_active"


@dataclass(frozen=True)
class Renewal:
    status: RenewalStatus
    term: AcademicTerm | None
    application_id: int | None


def renewal_for(award: Award, term: AcademicTerm | None) -> Renewal:
    """Where the award stands for `term`. The window is not part of it: callers say that."""
    if award.status != Award.Status.ACTIVE:
        return Renewal(RenewalStatus.NOT_ACTIVE, term, None)
    if term is None:
        return Renewal(RenewalStatus.NO_TERM, None, None)
    if term.term == AcademicTerm.Term.SUMMER:
        return Renewal(RenewalStatus.SUMMER, term, None)
    recorded = ScholarTerm.objects.filter(award=award, term=term).exists()
    statuses = dict(
        Application.objects.filter(
            award=award, term=term, kind=Application.Kind.RENEWAL
        ).values_list("status", "pk")
    )
    return _renewal_from(term, recorded=recorded, statuses=statuses)


def _renewal_from(term: AcademicTerm, *, recorded: bool, statuses: dict[str, int]) -> Renewal:
    """`renewal_for` past the award and term checks, on rows the caller already read."""
    if recorded:
        return Renewal(RenewalStatus.RENEWED, term, None)
    for status in Application.OPEN_STATUSES:
        if status in statuses:
            return Renewal(RenewalStatus.OPEN, term, statuses[status])
    if Application.Status.APPROVED in statuses:
        return Renewal(RenewalStatus.RENEWED, term, None)
    if Application.Status.REJECTED in statuses:
        return Renewal(RenewalStatus.REJECTED, term, None)
    return Renewal(RenewalStatus.DUE, term, None)


def renewal_due_q(term: AcademicTerm) -> Q:
    """Awards due to renew for `term` (as `renewal_for` gives DUE), window aside."""
    if term.term == AcademicTerm.Term.SUMMER:
        return Q(pk__in=[])
    recorded = ScholarTerm.objects.filter(award=OuterRef("pk"), term=term)
    settled = Application.objects.filter(
        award=OuterRef("pk"),
        term=term,
        kind=Application.Kind.RENEWAL,
        status__in=SETTLING_STATUSES,
    )
    return Q(status=Award.Status.ACTIVE) & ~Q(Exists(recorded)) & ~Q(Exists(settled))


def renewal_tier(award: Award, term: AcademicTerm) -> BenefitTier | None:
    """The in-force row with the award's tier code: a re-price keeps the scholar's tier."""
    code = award.tier.code
    return next((tier for tier in tiers_in_force(award.program, term) if tier.code == code), None)


@dataclass(frozen=True)
class ScholarshipCard:
    award: Award
    terms: list[ScholarTerm]  # newest first
    renewal: Renewal
    window_reason: str  # why renewing is closed today ("" when the window is open)


def scholarships_for_student(user: User, *, today: date) -> list[ScholarshipCard]:
    """The student's awards with their term records and renewal state, in a fixed number of
    queries whatever the number of awards."""
    awards = list(
        Award.objects.filter(profile__user=user)
        .select_related("program", "tier", "started_term", "ended_term")
        .order_by("program__name", "pk")
    )
    if not awards:
        return []
    term = application_term(today)
    records: dict[int, list[ScholarTerm]] = {award.pk: [] for award in awards}
    for record in (
        ScholarTerm.objects.filter(award__in=awards)
        .select_related("term", "school", "tier")
        .order_by("-term__sort_key", "-pk")
    ):
        records[record.award_id].append(record)
    statuses: dict[int, dict[str, int]] = {award.pk: {} for award in awards}
    if term is not None:
        for award_id, status, pk in Application.objects.filter(
            award__in=awards, term=term, kind=Application.Kind.RENEWAL
        ).values_list("award_id", "status", "pk"):
            assert award_id is not None
            statuses[award_id][status] = pk
    cards = []
    for award in awards:
        if award.status != Award.Status.ACTIVE:
            renewal = Renewal(RenewalStatus.NOT_ACTIVE, term, None)
        elif term is None:
            renewal = Renewal(RenewalStatus.NO_TERM, None, None)
        elif term.term == AcademicTerm.Term.SUMMER:
            renewal = Renewal(RenewalStatus.SUMMER, term, None)
        else:
            recorded = any(record.term_id == term.pk for record in records[award.pk])
            renewal = _renewal_from(term, recorded=recorded, statuses=statuses[award.pk])
        cards.append(
            ScholarshipCard(
                award=award,
                terms=records[award.pk],
                renewal=renewal,
                window_reason=window_reason(award.program, today, term),
            )
        )
    return cards


def _latest(field: str) -> Subquery:
    return Subquery(
        ScholarTerm.objects.filter(award=OuterRef("pk"))
        .order_by("-term__sort_key", "-pk")
        .values(field)[:1]
    )


def with_latest_term(rows: QuerySet[Award]) -> QuerySet[Award]:
    """Annotate each award with its latest term record (by term order) and its record count."""
    latest_school = Subquery(
        ScholarTerm.objects.filter(award=OuterRef("pk"))
        .order_by("-term__sort_key", "-pk")
        .annotate(name=Coalesce("school__name", "school_name"))
        .values("name")[:1]
    )
    count = Subquery(
        ScholarTerm.objects.filter(award=OuterRef("pk"))
        .order_by()
        .values("award")
        .annotate(n=Count("pk"))
        .values("n")[:1]
    )
    return rows.annotate(
        latest_term_id=_latest("term_id"),
        latest_gwa=_latest("gwa"),
        latest_gwa_scale=_latest("gwa_scale"),
        latest_units=_latest("units"),
        latest_year_level=_latest("year_level"),
        latest_course=_latest("course"),
        latest_school_name=latest_school,
        term_count=Coalesce(count, Value(0)),
    )


def _renewal_closed(program: Program, term: AcademicTerm | None, today: date) -> bool:
    return term is not None and window_state(program, today) == "closed"


def at_risk_q(program: Program, term: AcademicTerm | None, today: date) -> Q:
    """Active awards at risk (a proposal pending §18 Q5), on a `with_latest_term` queryset."""
    risks = Q(pk__in=[])
    if program.renewal_min_gwa_percent is not None:
        risks |= Q(latest_gwa_scale="percent", latest_gwa__lt=program.renewal_min_gwa_percent)
    if program.renewal_max_gwa_one_to_five is not None:
        risks |= Q(
            latest_gwa_scale="one_to_five", latest_gwa__gt=program.renewal_max_gwa_one_to_five
        )
    if program.renewal_min_units is not None:
        risks |= Q(latest_units__lt=program.renewal_min_units)
    if _renewal_closed(program, term, today):
        assert term is not None
        risks |= renewal_due_q(term)
    return Q(status=Award.Status.ACTIVE) & risks


def at_risk_reasons(
    award: Award, program: Program, term: AcademicTerm | None, today: date
) -> list[str]:
    """Why an annotated active award is at risk, as sentences for staff; empty when it isn't."""
    if award.status != Award.Status.ACTIVE:
        return []
    reasons = []
    gwa, scale = award.latest_gwa, award.latest_gwa_scale  # type: ignore[attr-defined]
    if gwa is not None:
        low = (
            scale == "percent"
            and program.renewal_min_gwa_percent is not None
            and gwa < program.renewal_min_gwa_percent
        ) or (
            scale == "one_to_five"
            and program.renewal_max_gwa_one_to_five is not None
            and gwa > program.renewal_max_gwa_one_to_five
        )
        if low:
            reasons.append(f"Last term's GWA of {gwa} misses the renewal mark.")
    units = award.latest_units  # type: ignore[attr-defined]
    if units is not None and program.renewal_min_units is not None:
        if units < program.renewal_min_units:
            reasons.append(f"Last term's {units} units are under the renewal minimum.")
    if _renewal_closed(program, term, today):
        if renewal_for(award, term).status == RenewalStatus.DUE:
            reasons.append("Not renewed, and renewals have closed.")
    return reasons


SCHOLAR_TABS: dict[str, str] = {
    "active": "Active",
    "suspended": "Suspended",
    "inactive": "Inactive",
    "graduated": "Graduated",
    "at_risk": "At risk",
    "not_renewed": "Not renewed",
    "all": "All",
}
DEFAULT_SCHOLAR_TAB = "active"


@dataclass(frozen=True)
class ScholarFilters:
    status: str = DEFAULT_SCHOLAR_TAB
    q: str = ""
    tier: str = ""


def parse_scholar_filters(params: QueryDict, program: Program) -> ScholarFilters:
    """Unknown values fall back to the defaults, never an error."""
    status = params.get("status", "")
    if status not in SCHOLAR_TABS:
        status = DEFAULT_SCHOLAR_TAB
    tier = params.get("tier", "")
    if tier and not program.tiers.filter(code=tier).exists():
        tier = ""
    return ScholarFilters(
        status=status, q=params.get("q", "").replace("\x00", "").strip()[:200], tier=tier
    )


def _program_awards(program: Program) -> QuerySet[Award]:
    return with_latest_term(
        Award.objects.filter(program=program).select_related(
            "profile", "profile__user", "tier", "started_term"
        )
    )


def scholars(
    program: Program, filters: ScholarFilters, *, term: AcademicTerm | None, today: date
) -> QuerySet[Award]:
    rows = _program_awards(program)
    if filters.status in Award.Status.values:
        rows = rows.filter(status=filters.status)
    elif filters.status == "at_risk":
        rows = rows.filter(at_risk_q(program, term, today))
    elif filters.status == "not_renewed":
        rows = rows.filter(renewal_due_q(term)) if term is not None else rows.none()
    if filters.tier:
        rows = rows.filter(tier__code=filters.tier)
    for word in filters.q.split():
        rows = rows.filter(
            Q(profile__first_name__icontains=word) | Q(profile__last_name__icontains=word)
        )
    return rows.order_by("profile__last_name", "profile__first_name", "pk")


def staff_award(program: Program, pk: int) -> Award:
    """One of the program's awards, annotated; another program's id is a 404."""
    award = _program_awards(program).filter(pk=pk).first()
    if award is None:
        raise Http404("No such scholar.")
    return award
