from dataclasses import dataclass
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


def tiers_in_force_for(programs: list[Program], term: AcademicTerm) -> dict[int, list[BenefitTier]]:
    """`tiers_in_force` for several programs in one query, keyed by program id."""
    latest = (
        BenefitTier.objects.filter(
            program__in=programs, effective_from__sort_key__lte=term.sort_key
        )
        .order_by("program_id", "code", "-effective_from__sort_key")
        .distinct("program_id", "code")
    )
    found: dict[int, list[BenefitTier]] = {program.pk: [] for program in programs}
    for tier in latest:
        if tier.is_active:
            found[tier.program_id].append(tier)
    return {
        key: sorted(tiers, key=lambda tier: (tier.sort_order, tier.name))
        for key, tiers in found.items()
    }


def required_documents_for(
    program: Program, kind: Literal["new", "renewal"]
) -> QuerySet[RequiredDocument]:
    """The active requirements for this kind; a switched-off one is gone everywhere."""
    return program.required_documents.filter(
        applies_to__in=[kind, RequiredDocument.AppliesTo.BOTH], is_active=True
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
    if has_tier and program.required_documents.filter(is_active=True).exists():
        return None
    return SETUP_NEEDED.format(name=program.name)


def deactivation_counts(program: Program) -> tuple[int, int]:
    """Waiting applications and payouts in progress (prepared or approved), which keep a
    program open. Returned applications count as waiting: a student may resubmit one, and in a
    closed program nobody would see it."""
    from apps.applications.models import Application
    from apps.money.models import Disbursement

    waiting = Application.objects.filter(
        program=program,
        status__in=[
            Application.Status.SUBMITTED,
            Application.Status.UNDER_REVIEW,
            Application.Status.RETURNED,
        ],
    ).count()
    payouts = Disbursement.objects.filter(
        schedule__program=program,
        status__in=[Disbursement.Status.PENDING, Disbursement.Status.APPROVED],
    ).count()
    return waiting, payouts


@dataclass(frozen=True)
class TierLine:
    code: str
    name: str
    in_force: (
        BenefitTier | None
    )  # the row in force for the current term (None: not yet, or stopped)
    upcoming: list[BenefitTier]  # rows effective after the current term, earliest first


def tier_codes(program: Program, term: AcademicTerm | None) -> list[TierLine]:
    """Every tier code of the program, with the row in force now and the changes to come. One
    query whatever the number of rows."""
    rows = list(
        BenefitTier.objects.filter(program=program)
        .select_related("effective_from")
        .order_by("code", "effective_from__sort_key")
    )
    key = term.sort_key if term is not None else None
    lines: dict[str, TierLine] = {}
    for code in dict.fromkeys(row.code for row in rows):
        mine = [row for row in rows if row.code == code]
        now = [row for row in mine if key is not None and row.effective_from.sort_key <= key]
        current = now[-1] if now and now[-1].is_active else None
        later = [row for row in mine if key is None or row.effective_from.sort_key > key]
        latest = current or mine[-1]
        lines[code] = TierLine(code=code, name=latest.name, in_force=current, upcoming=later)
    return sorted(
        lines.values(),
        key=lambda line: (
            line.in_force.sort_order if line.in_force else 0,
            line.name,
        ),
    )


def tier_in_use(tier: BenefitTier) -> bool:
    """Whether any award, term record or application points at this exact row."""
    from apps.applications.models import Application
    from apps.awards.models import Award, ScholarTerm

    return (
        Award.objects.filter(tier=tier).exists()
        or ScholarTerm.objects.filter(tier=tier).exists()
        or Application.objects.filter(requested_tier=tier).exists()
    )
