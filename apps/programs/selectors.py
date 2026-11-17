from datetime import date
from decimal import Decimal
from typing import Literal

from django.db.models import QuerySet

from apps.accounts.models import User
from apps.programs.models import (
    AcademicTerm,
    BenefitTier,
    Program,
    ProgramMembership,
    RequiredDocument,
)


def programs_for(user: User) -> QuerySet[Program]:
    """Active programs this user may work in: all for the office, their own for staff."""
    active = Program.objects.filter(is_active=True)
    if user.is_super_admin:
        return active
    if user.is_program_staff:
        return active.filter(memberships__user=user)
    return Program.objects.none()


def membership_for(user: User, program: Program) -> ProgramMembership | None:
    return ProgramMembership.objects.filter(user=user, program=program).first()


def current_term() -> AcademicTerm | None:
    return AcademicTerm.objects.filter(is_current=True).first()


def application_term(today: date) -> AcademicTerm | None:
    """The flagged term (even if its dates exclude today), else the term containing today."""
    flagged = current_term()
    if flagged is not None:
        return flagged
    return AcademicTerm.objects.filter(starts_on__lte=today, ends_on__gte=today).first()


def window_state(program: Program, today: date) -> Literal["open", "not_yet", "closed"]:
    """Both ends inclusive; a missing end is unbounded."""
    if program.applications_open_on is not None and today < program.applications_open_on:
        return "not_yet"
    if program.applications_close_on is not None and today > program.applications_close_on:
        return "closed"
    return "open"


def tiers_in_force(program: Program, term: AcademicTerm) -> list[BenefitTier]:
    """Per code, the latest row effective by this term; an inactive latest row ends the tier."""
    latest = (
        BenefitTier.objects.filter(program=program, effective_from__sort_key__lte=term.sort_key)
        .order_by("code", "-effective_from__sort_key")
        .distinct("code")
    )
    live = [tier for tier in latest if tier.is_active]
    return sorted(live, key=lambda tier: (tier.sort_order, tier.name))


def required_documents_for(
    program: Program, kind: Literal["new", "renewal"]
) -> QuerySet[RequiredDocument]:
    return program.required_documents.filter(
        applies_to__in=[kind, RequiredDocument.AppliesTo.BOTH]
    ).order_by("sort_order", "pk")


def _plain(value: Decimal) -> str:
    """80.00 → "80", 2.50 → "2.5": a rule's number without trailing zeros."""
    return format(value.normalize(), "f")


def renewal_rule_text(program: Program) -> str:
    """What a scholar keeps up to renew, after "To renew:"; "" when the program sets no rule."""
    marks = []
    if program.renewal_min_gwa_percent is not None:
        marks.append(f"a GWA of {_plain(program.renewal_min_gwa_percent)}% or better")
    if program.renewal_max_gwa_one_to_five is not None:
        marks.append(
            f"a GWA of {_plain(program.renewal_max_gwa_one_to_five)} or better on the 1–5 scale"
        )
    rest = []
    if program.renewal_min_units is not None:
        rest.append(f"at least {program.renewal_min_units} units")
    if program.renewal_no_failing_grades:
        rest.append("no failing grades")
    if marks:
        text = "keep " + " or ".join(marks)
        if rest:
            text += " with " + " and ".join(rest)
        return text + "."
    if rest:
        return "keep " + " and ".join(rest) + "."
    return ""


SETUP_NEEDED = "Add an allowance tier and a required document before opening {name}."


def activation_problem(program: Program, term: AcademicTerm | None) -> str | None:
    """Why the program can't open yet: it needs a tier in force now and a required document."""
    has_tier = term is not None and bool(tiers_in_force(program, term))
    if has_tier and program.required_documents.exists():
        return None
    return SETUP_NEEDED.format(name=program.name)


def deactivation_counts(program: Program) -> tuple[int, int]:
    """Waiting applications and payouts in progress (prepared or approved), which keep a
    program open."""
    from apps.applications.models import Application
    from apps.money.models import Disbursement

    waiting = Application.objects.filter(
        program=program,
        status__in=[Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW],
    ).count()
    payouts = Disbursement.objects.filter(
        schedule__program=program,
        status__in=[Disbursement.Status.PENDING, Disbursement.Status.APPROVED],
    ).count()
    return waiting, payouts
