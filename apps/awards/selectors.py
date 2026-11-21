from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.contrib.postgres.aggregates import StringAgg
from django.db.models import (
    Count,
    Exists,
    F,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    TextField,
    Value,
)
from django.db.models.functions import Coalesce
from django.http import Http404, QueryDict

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.core.params import positive_id
from apps.matching.eligibility import window_reason
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import application_term, tiers_in_force
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


ONE_SCHOLARSHIP = (
    "You already hold the {program} scholarship. A student can hold one scholarship at a time."
)


def held_awards(profile: StudentProfile) -> list[Award]:
    """The student's active and on-hold awards, earliest first, with their programs."""
    return list(
        Award.objects.filter(profile=profile, status__in=Award.HELD_STATUSES)
        .select_related("program")
        .order_by("started_term__sort_key", "pk")
    )


def held_award_elsewhere(profile: StudentProfile, program: Program) -> Award | None:
    """An active or on-hold award in another program (spec §4.5: one scholarship at a time).

    Rows from before the rule may hold several: the earliest one stands for them. Write paths
    call this under the StudentProfile row lock, which every award write takes first."""
    return (
        Award.objects.filter(profile=profile, status__in=Award.HELD_STATUSES)
        .exclude(program=program)
        .select_related("program")
        .order_by("started_term__sort_key", "pk")
        .first()
    )


def one_scholarship(award: Award) -> str:
    """The refusal for a student who already holds `award` in another program."""
    return ONE_SCHOLARSHIP.format(program=award.program.name)


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


SCHOLAR_TABS: dict[str, str] = {
    "active": "Active",
    "suspended": "Suspended",
    "inactive": "Inactive",
    "graduated": "Graduated",
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
    program: Program, filters: ScholarFilters, *, term: AcademicTerm | None
) -> QuerySet[Award]:
    rows = _program_awards(program)
    if filters.status in Award.Status.values:
        rows = rows.filter(status=filters.status)
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


@dataclass(frozen=True)
class ScholarRecord:
    terms: list[ScholarTerm]  # newest first
    applications: list[Application]  # the source application, then renewals, newest first
    renewal: Renewal


def scholar_record(award: Award, *, term: AcademicTerm | None) -> ScholarRecord:
    """Everything the scholar's record page shows; `award` comes from `staff_award`."""
    terms = list(
        ScholarTerm.objects.filter(award=award)
        .select_related("term", "school", "tier", "merit_confirmed_by")
        .order_by("-term__sort_key", "-pk")
    )
    applications = list(
        Application.objects.filter(Q(source_award=award) | Q(award=award))
        .select_related("term")
        .order_by("-term__sort_key", "-pk")
    )
    return ScholarRecord(
        terms=terms,
        applications=applications,
        renewal=renewal_for(award, term),
    )


def next_year_level(award: Award, term: AcademicTerm) -> int | None:
    """The latest record's year level, plus one when `term` is in a later school year."""
    latest = (
        ScholarTerm.objects.filter(award=award, term__sort_key__lt=term.sort_key)
        .select_related("term")
        .order_by("-term__sort_key")
        .first()
    )
    if latest is None or latest.year_level is None:
        return None
    if term.school_year_start > latest.term.school_year_start:
        return latest.year_level + 1
    return latest.year_level


@dataclass(frozen=True)
class RolloverResult:
    withdrawn: int
    graduated: int


def stale_applications(term: AcademicTerm) -> QuerySet[Application]:
    """Unfinished applications (draft or returned) of terms before `term`: the rollover withdraws
    them. Submitted and under-review rows stay for staff to decide."""
    return Application.objects.filter(
        status__in=[Application.Status.DRAFT, Application.Status.RETURNED],
        term__sort_key__lt=term.sort_key,
    )


def graduating_awards() -> QuerySet[Award]:
    """Held awards whose program has a term limit and that have reached it. Only 1st and 2nd
    semester records count: summer never renews (M14)."""
    regular = Q(terms__term__term__in=[AcademicTerm.Term.FIRST, AcademicTerm.Term.SECOND])
    return (
        Award.objects.filter(status__in=Award.HELD_STATUSES, program__max_terms__isnull=False)
        .annotate(records=Count("terms", filter=regular))
        .filter(records__gte=F("program__max_terms"))
    )


def rollover_preview(term: AcademicTerm) -> RolloverResult:
    """What making `term` current would do. Counts only."""
    return RolloverResult(
        withdrawn=stale_applications(term).count(), graduated=graduating_awards().count()
    )


def pick_tier(rows: list[BenefitTier], term: AcademicTerm) -> BenefitTier | None:
    """Of one code's rows (with `effective_from` loaded), the one a new award starting in `term`
    gets: the latest row effective by `term`, unless that row ended the tier. When no row is
    effective yet (the seed's tiers start in the current school year), the earliest active row."""
    effective = [row for row in rows if row.effective_from.sort_key <= term.sort_key]
    if effective:
        latest = max(effective, key=lambda row: (row.effective_from.sort_key, row.pk))
        return latest if latest.is_active else None
    active = [row for row in rows if row.is_active]
    return min(active, key=lambda row: (row.effective_from.sort_key, row.pk), default=None)


def start_tier(program: Program, code: str, term: AcademicTerm) -> BenefitTier | None:
    """The tier with this code that a new award starting in `term` gets (see `pick_tier`)."""
    rows = BenefitTier.objects.filter(program=program, code=code).select_related("effective_from")
    return pick_tier(list(rows), term)


def program_profiles(program: Program) -> QuerySet[StudentProfile]:
    """The students this program knows: created for it, holding any award in it, or with a
    submitted application to it. Staff never search beyond these (spec §18 Q16)."""
    holds = Award.objects.filter(profile=OuterRef("pk"), program=program)
    applied = Application.objects.filter(
        profile=OuterRef("pk"), program=program, submitted_at__isnull=False
    )
    return StudentProfile.objects.filter(
        Q(created_for=program) | Exists(holds) | Exists(applied)
    ).order_by("last_name", "first_name", "pk")


def addable_profiles(program: Program, q: str) -> QuerySet[StudentProfile]:
    """The program's students for the Add scholar picker; every word of `q` must match a name.

    Each row carries `holds` (an active or on-hold award in the program)."""
    rows = program_profiles(program).annotate(
        holds=Exists(
            Award.objects.filter(
                profile=OuterRef("pk"), program=program, status__in=Award.HELD_STATUSES
            )
        )
    )
    for word in q.split():
        rows = rows.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word))
    return rows


def active_counts(program_ids: list[int]) -> dict[int, int]:
    """Active awards per program, in one query; programs with none are left out."""
    rows = (
        Award.objects.filter(program_id__in=program_ids, status=Award.Status.ACTIVE)
        .values("program_id")
        .annotate(n=Count("pk"))
        .order_by()
    )
    return {row["program_id"]: row["n"] for row in rows}


# Scholars across programs (the office, M11c). No tier filter (codes are per program).
OFFICE_SCHOLAR_TABS: dict[str, str] = {
    "active": "Active",
    "suspended": "Suspended",
    "inactive": "Inactive",
    "graduated": "Graduated",
    "all": "All",
}


@dataclass(frozen=True)
class OfficeScholarFilters:
    status: str = DEFAULT_SCHOLAR_TAB
    q: str = ""
    program: int | None = None


def parse_office_scholar_filters(params: QueryDict) -> OfficeScholarFilters:
    """Unknown values fall back to the defaults, never an error."""
    status = params.get("status", "")
    if status not in OFFICE_SCHOLAR_TABS:
        status = DEFAULT_SCHOLAR_TAB
    program = positive_id(params.get("program", ""))
    if program is not None and not Program.objects.filter(pk=program).exists():
        program = None
    return OfficeScholarFilters(
        status=status, q=params.get("q", "").replace("\x00", "").strip()[:200], program=program
    )


def office_scholars(filters: OfficeScholarFilters) -> QuerySet[Award]:
    """Awards across programs, annotated with the latest term and `other_programs` (the names of
    the profile's other active awards' programs, by name)."""
    active = Award.objects.filter(profile_id=OuterRef("profile_id"), status=Award.Status.ACTIVE)
    others = Subquery(
        active.exclude(pk=OuterRef("pk"))
        .order_by()
        .values("profile_id")
        .annotate(names=StringAgg("program__name", ", ", order_by="program__name"))
        .values("names")[:1]
    )
    rows = with_latest_term(
        Award.objects.select_related("program", "profile", "profile__user", "tier", "started_term")
    ).annotate(other_programs=Coalesce(others, Value(""), output_field=TextField()))
    if filters.status in Award.Status.values:
        rows = rows.filter(status=filters.status)
    if filters.program is not None:
        rows = rows.filter(program_id=filters.program)
    for word in filters.q.split():
        rows = rows.filter(
            Q(profile__first_name__icontains=word) | Q(profile__last_name__icontains=word)
        )
    return rows.order_by("profile__last_name", "profile__first_name", "program__name", "pk")
