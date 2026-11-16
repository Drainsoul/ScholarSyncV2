from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.db.models import Exists, OuterRef, Q

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
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
