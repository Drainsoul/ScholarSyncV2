"""Starter reference data for ``seed_programs`` (v1's rules, tiers and document list)."""

from decimal import Decimal
from typing import Any

from apps.files.policy import JPEG, MB, PDF, PNG
from apps.programs.models import RequiredDocument, School

ALL_TYPES = [PDF, JPEG, PNG]
IMG_TYPES = [JPEG, PNG]
MAX_BYTES = 10 * MB

STARTER_SCHOOLS: list[dict[str, Any]] = [
    {
        "name": "Taguig City University",
        "type": School.Type.LCU,
        "grading_scale": School.Scale.PERCENT,
        "is_in_taguig": True,
    },
    {
        "name": "University of the Philippines",
        "type": School.Type.SUC,
        "grading_scale": School.Scale.ONE_TO_FIVE,
    },
    {
        "name": "University of Santo Tomas",
        "type": School.Type.PRIVATE,
        "grading_scale": School.Scale.ONE_TO_FIVE,
    },
]

STARTER_PROGRAMS: list[dict[str, Any]] = [
    {
        "slug": "tcu-ceaa",
        "name": "TCU CEAA Scholarship",
        "description": (
            "The Taguig City University City Educational Assistance Allowance "
            "gives scholars an allowance each semester."
        ),
        "rules": {
            "min_gwa_percent": Decimal("80"),
            "renewal_min_gwa_percent": Decimal("80"),
            "renewal_min_units": 15,
            # §18 Q4, the TCU-CEAA site: no failing, incomplete, blank or dropped subjects.
            "renewal_no_failing_grades": True,
        },
        "school_names": ["Taguig City University"],
        "tiers": [("standard", "Standard", Decimal("5000.00"), Decimal("10000.00"))],
    },
    {
        "slug": "lani",
        "name": "LANI Scholarship Program",
        "description": (
            "Lifeline Assistance for Neighbors In-need is a City of Taguig "
            "scholarship that pays scholars an allowance each semester."
        ),
        "rules": {
            "min_gwa_percent": Decimal("75"),
            # 3.00 is the 1-5 passing mark, as 75% is on the percent scale. Renewal: v1's 2.50 on
            # the 1.0-5.0 scale (§18 Q4; the LANI page states no renewal threshold).
            "max_gwa_one_to_five": Decimal("3.00"),
            "renewal_max_gwa_one_to_five": Decimal("2.50"),
            "renewal_min_units": 15,
            "renewal_no_failing_grades": True,
        },
        "school_names": [],
        # Spec §18 Q2: the TCU LANI page's amounts are per school year; payouts are per term, so
        # halved. Merit (the top of the page's range) is for Premier, Full and Priority only.
        # LEAD has no published amount: v1's figures stay until the maintainer confirms them.
        "tiers": [
            ("premier", "Premier", Decimal("20000.00"), Decimal("25000.00")),
            ("full", "Full", Decimal("20000.00"), Decimal("25000.00")),
            ("priority", "Priority", Decimal("20000.00"), Decimal("25000.00")),
            ("basic-plus", "Basic Plus", Decimal("7500.00"), Decimal("0.00")),
            ("suc-lcu", "SUC/LCU", Decimal("5000.00"), Decimal("0.00")),
            ("basic", "Basic", Decimal("5000.00"), Decimal("0.00")),
            ("review", "Review", Decimal("10000.00"), Decimal("0.00")),
            ("review-retake", "Review (retake)", Decimal("5000.00"), Decimal("0.00")),
            ("lead", "LEAD", Decimal("30000.00"), Decimal("50000.00")),
        ],
    },
]

_NEW = RequiredDocument.AppliesTo.NEW
_RENEWAL = RequiredDocument.AppliesTo.RENEWAL
_BOTH = RequiredDocument.AppliesTo.BOTH

_IDS = (
    "e-Card/UMID, Driver's License, Passport, SSS ID, Voter's ID, BIR (TIN ID), PWD ID, "
    "Solo Parent ID, Barangay ID, Postal ID, PhilHealth ID, National ID."
)
_PRINCIPAL = "Certificate from the principal of the school you graduated from."
_PSA = "Issued by PSA/NSO/Civil Registry Office."

# (code, label, applies_to, is_required, accepted_types, help_text)
STARTER_DOCUMENTS: list[tuple[str, str, str, bool, list[str], str]] = [
    (
        "photo-2x2",
        "2x2 ID Picture",
        _BOTH,
        True,
        IMG_TYPES,
        "Recent 2x2 ID picture with white background.",
    ),
    (
        "jhs-certificate",
        "Junior High School Certificate/Grade 10 Report Card",
        _NEW,
        True,
        ALL_TYPES,
        _PRINCIPAL,
    ),
    (
        "shs-diploma",
        "Senior High School Diploma/Grade 12 Report Card",
        _NEW,
        True,
        ALL_TYPES,
        _PRINCIPAL,
    ),
    (
        "valid-id",
        "School ID or Valid Government-issued ID",
        _NEW,
        True,
        ALL_TYPES,
        f"Acceptable IDs: {_IDS}",
    ),
    ("birth-certificate", "Birth Certificate", _BOTH, True, ALL_TYPES, _PSA),
    (
        "voters-certification",
        "Voter's Certification",
        _NEW,
        True,
        ALL_TYPES,
        "COMELEC certification showing a parent is a registered voter of Taguig "
        "(issued after May 2022). Include your own if you are 18 or older.",
    ),
    (
        "registration-form",
        "Official Form/Registration Form/Certificate of Matriculation",
        _RENEWAL,
        True,
        ALL_TYPES,
        "Authenticated/certified true copy for the semester or term you are applying for.",
    ),
    (
        "grades",
        "Certificate of Grades",
        _RENEWAL,
        True,
        ALL_TYPES,
        "Original, authenticated or certified true copy of last semester's grades with the "
        "school seal or an official signature. For trimester and quarter terms, grades for "
        "the past two terms.",
    ),
    (
        "valid-id-renewal",
        "School ID or Valid Government-issued ID",
        _RENEWAL,
        True,
        ALL_TYPES,
        "Photocopy within its validity period, back-to-back on one page, with your printed "
        "name and signature. Acceptable IDs: School ID, " + _IDS,
    ),
    (
        "voters-certification-renewal",
        "Voter's Certification",
        _RENEWAL,
        True,
        ALL_TYPES,
        "COMELEC certification showing a parent is a registered and active voter of Taguig "
        "(issued after May 2022). Include your own if you are 18 or older.",
    ),
    (
        "form-137",
        "Certified True Copy of Elementary/High School Form 137",
        _BOTH,
        False,
        ALL_TYPES,
        "If you didn't complete junior high school in Taguig but graduated senior high "
        "school in Taguig or a nearby LGU.",
    ),
    (
        "als-certificate",
        "ALS Certificate",
        _BOTH,
        False,
        ALL_TYPES,
        "If you are an ALS graduate.",
    ),
    (
        "parent-death-certificate",
        "Death Certificate (Parent)",
        _BOTH,
        False,
        ALL_TYPES,
        f"If a parent has died. {_PSA}",
    ),
    (
        "ofw-parent-documents",
        "Work Contract/VISA/Passport (OFW Parents)",
        _BOTH,
        False,
        ALL_TYPES,
        "If one or both parents are OFWs.",
    ),
]
