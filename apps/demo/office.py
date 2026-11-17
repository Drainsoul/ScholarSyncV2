"""Demo samples for the M11b screens: a closed program ready to open, a deactivated staff
account and an upcoming TCU CEAA tier change. Every step skips what already exists."""

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts import services as accounts
from apps.accounts.models import User
from apps.accounts.services import create_staff_user
from apps.files.policy import JPEG, MB, PDF, PNG
from apps.programs import services as programs
from apps.programs.models import AcademicTerm, BenefitTier, Program, RequiredDocument
from apps.programs.selectors import current_term

logger = logging.getLogger(__name__)

YOUTH_SLUG = "youth-grant"
FORMER_STAFF = "former.staff@scholarsync.test"
NEXT_YEAR_BASE = Decimal("5500.00")
NEXT_YEAR_MERIT = Decimal("11000.00")


def _office() -> User | None:
    return User.objects.filter(email__iexact="office@scholarsync.test").first()


def _closed_program(office: User) -> None:
    """Taguig Youth Grant: closed, with a tier and a document, so a visitor can open it."""
    if Program.objects.filter(slug=YOUTH_SLUG).exists():
        return
    term = current_term()
    if term is None:
        return
    program = programs.create_program(
        actor=office,
        slug=YOUTH_SLUG,
        name="Taguig Youth Grant",
        description="A sample program the office hasn't opened yet.",
    )
    programs.add_tier(
        actor=office,
        program=program,
        code="standard",
        name="Standard",
        base_amount=Decimal("4000.00"),
        merit_amount=Decimal("0.00"),
        effective_from=term,
        sort_order=0,
    )
    programs.add_document(
        actor=office,
        program=program,
        data={
            "code": "certificate-of-registration",
            "label": "Certificate of registration",
            "help_text": "This term's registration form from your school.",
            "applies_to": RequiredDocument.AppliesTo.BOTH,
            "is_required": True,
            "accepted_types": [PDF, JPEG, PNG],
            "max_bytes": 10 * MB,
            "sort_order": 0,
        },
    )


def _former_staff(office: User) -> None:
    """A deactivated staff account with no programs, for the Staff list's status column."""
    if User.objects.filter(email__iexact=FORMER_STAFF).exists():
        return
    user = create_staff_user(
        actor=None, email=FORMER_STAFF, full_name="Ramil Ocampo", role=User.Role.STAFF
    )
    accounts.set_account_active(actor=office, user=user, active=False)


def _upcoming_tier_change(office: User) -> None:
    """TCU CEAA pays more from next school year's 1st semester, when that term exists."""
    program = Program.objects.filter(slug="tcu-ceaa").first()
    term = current_term()
    if program is None or term is None:
        return
    next_first = AcademicTerm.objects.filter(
        school_year_start=term.school_year_start + 1, term=AcademicTerm.Term.FIRST
    ).first()
    if next_first is None:
        return
    if BenefitTier.objects.filter(program=program, effective_from=next_first).exists():
        return
    programs.change_tier_amounts(
        actor=office,
        program=program,
        code="standard",
        base_amount=NEXT_YEAR_BASE,
        merit_amount=NEXT_YEAR_MERIT,
        effective_from=next_first,
    )


def give_office_samples() -> None:
    office = _office()
    if office is None:
        return
    try:
        with transaction.atomic():
            _closed_program(office)
            _former_staff(office)
            _upcoming_tier_change(office)
    except ValidationError as error:
        # Log only the error class: service sentences can hold names.
        logger.warning("Demo office samples skipped (%s).", type(error).__name__)
