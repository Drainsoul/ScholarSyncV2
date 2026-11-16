from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Exists, OuterRef, Q

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.selectors import tiers_in_force
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
    if ScholarTerm.objects.filter(award=award, term=term).exists():
        return Renewal(RenewalStatus.RENEWED, term, None)
    statuses = dict(
        Application.objects.filter(
            award=award, term=term, kind=Application.Kind.RENEWAL
        ).values_list("status", "pk")
    )
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
