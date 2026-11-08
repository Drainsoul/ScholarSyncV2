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
