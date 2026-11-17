"""Sample applicants and sample files for the staff review queue. Fixed values, no real people."""

import base64
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PDF_TYPE = "application/pdf"
PNG_TYPE = "image/png"

_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
# A 20x20 solid PNG, for the requirements that only accept pictures (the 2x2 ID picture).
SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAAGklEQVR4nGMQaDhANmIY1TyqeVTzqOaB1QwANQINH6BXGBYAAAAASUVORK5CYII="
)
# Exactly one kilobyte, as in the end-to-end tests.
SAMPLE_PDF = _PDF + b"%" + b"0" * (1024 - len(_PDF) - 2) + b"\n"

DECLINE_REASON = "The scan is too dark to read."
RETURN_REASON = "Upload a clearer copy of your certificate of registration."


@dataclass(frozen=True)
class SampleApplicant:
    email: str
    first_name: str
    last_name: str
    birth_date: date
    state: str  # submitted | under_review | returned | approved


SAMPLE_APPLICANTS: tuple[SampleApplicant, ...] = (
    SampleApplicant(
        "applicant1@scholarsync.test", "Maria", "Dela Cruz", date(2006, 1, 22), "submitted"
    ),
    SampleApplicant(
        "applicant2@scholarsync.test", "Jose", "Santos", date(2005, 11, 3), "submitted2"
    ),
    SampleApplicant(
        "applicant3@scholarsync.test", "Angelica", "Reyes", date(2006, 6, 9), "under_review"
    ),
    SampleApplicant(
        "applicant4@scholarsync.test", "Miguel", "Bautista", date(2006, 8, 30), "returned"
    ),
    SampleApplicant(
        "applicant5@scholarsync.test", "Bianca", "Mendoza", date(2005, 12, 17), "approved"
    ),
)

OVERRIDE_REASON = "Walk-in applicant; the GWA shortfall was reviewed with the student's adviser."


@dataclass(frozen=True)
class WalkIn:
    email: str
    first_name: str
    last_name: str
    birth_date: date


# Staff-created profiles filed for at the office counter. The submitted one's GWA (78) is under
# TCU CEAA's 80% minimum, so staff override the GWA rule.
WALK_IN_SUBMITTED = WalkIn("ramon@scholarsync.test", "Ramon", "Aquino", date(2006, 9, 12))
WALK_IN_DRAFT = WalkIn("lorna@scholarsync.test", "Lorna", "Castillo", date(2006, 2, 27))


@dataclass(frozen=True)
class SampleScholar:
    email: str
    first_name: str
    last_name: str
    birth_date: date
    gwa: Decimal  # last term's GWA, on TCU's percent scale
    state: str  # due | at_risk | on_hold


# TCU CEAA scholars from the previous semester. Carmela is due to renew; Daniel's 78 is under
# CEAA's 80% renewal mark, so he is at risk; Elena's award is on hold. They share the demo
# password, so a visitor can sign in as Carmela and renew.
SAMPLE_SCHOLARS: tuple[SampleScholar, ...] = (
    SampleScholar(
        "scholar@scholarsync.test", "Carmela", "Villanueva", date(2005, 4, 18), Decimal("88"), "due"
    ),
    SampleScholar(
        "scholar2@scholarsync.test", "Daniel", "Ramos", date(2005, 9, 2), Decimal("78"), "at_risk"
    ),
    SampleScholar(
        "scholar3@scholarsync.test", "Elena", "Garcia", date(2006, 1, 7), Decimal("85"), "on_hold"
    ),
)

HOLD_REASON = "Waiting for the registrar to confirm enrolment."


@dataclass(frozen=True)
class ManualScholar:
    first_name: str
    last_name: str
    birth_date: date
    gwa: Decimal  # on TCU's percent scale


# A walk-in staff gave a TCU CEAA award by hand (M9b Add scholar): no account, never invited.
MANUAL_SCHOLAR = ManualScholar("Felipe", "Manalo", date(2005, 6, 18), Decimal("87.25"))
