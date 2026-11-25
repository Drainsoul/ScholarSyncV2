"""Sample applicants and sample files for the staff review queue. Fixed values, no real people."""

import struct
import zlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PDF_TYPE = "application/pdf"
PNG_TYPE = "image/png"


def _sample_pdf() -> bytes:
    """A valid one-page PDF (catalog, page tree, a page of text, a cross-reference table) that
    PDF viewers open. The text says it is a sample."""
    text = b"BT /F1 18 Tf 72 720 Td (ScholarSync sample document) Tj 0 -28 Td /F1 12 Tf "
    text += b"(Fictional demo file. No real person or data.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def _sample_png() -> bytes:
    """A 240x300 placeholder ID picture (a grey silhouette on light blue), drawn here so the demo
    has no image file and the review screen's preview shows something recognisable."""
    width, height = 240, 300
    background, figure = bytes((0xDB, 0xEA, 0xFE)), bytes((0x9C, 0xA3, 0xAF))
    rows = []
    for y in range(height):
        row = bytearray(1)  # filter byte 0: none
        for x in range(width):
            head = (x - 120) ** 2 + (y - 115) ** 2 <= 55**2
            shoulders = y >= 190 and (x - 120) ** 2 / 110**2 + (y - 300) ** 2 / 105**2 <= 1
            row += figure if head or shoulders else background
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        bytes((0x89,))
        + b"PNG"
        + bytes((13, 10, 26, 10))
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


# For the requirements that only accept pictures (the 2x2 ID picture).
SAMPLE_PNG = _sample_png()
SAMPLE_PDF = _sample_pdf()

DECLINE_REASON = "The scan is too dark to read."
RETURN_REASON = "Upload a clearer copy of your certificate of registration."


@dataclass(frozen=True)
class SampleApplicant:
    email: str
    first_name: str
    last_name: str
    birth_date: date
    state: str  # submitted | under_review | returned | approved | rejected | withdrawn
    # rev 36: the profile varies, so the lists look like real ones. The defaults are Carolyn's
    # (a TCU student who passes both programs' rules).
    sex: str = "female"
    barangay: str = "ususan"
    school: str = "Taguig City University"
    course: str = "BS Information Technology"
    gwa: Decimal = Decimal("88.50")  # on the school's scale (TCU: percent; UP and UST: 1-5)
    year_level: int = 2
    tier: str = ""  # the tier asked for: LANI has many, TCU CEAA one


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

# rev 36: two more TCU CEAA outcomes for the queue's tabs and the charts (they don't wait, so the
# "n of m waiting" pager is unchanged).
MORE_CEAA_APPLICANTS: tuple[SampleApplicant, ...] = (
    SampleApplicant(
        "applicant6@scholarsync.test",
        "Carlo",
        "Fernandez",
        date(2005, 7, 11),
        "rejected",
        sex="male",
        barangay="bagumbayan",
        course="BS Civil Engineering",
        gwa=Decimal("84.00"),
    ),
    SampleApplicant(
        "applicant7@scholarsync.test",
        "Jasmine",
        "Rivera",
        date(2006, 4, 25),
        "withdrawn",
        barangay="hagonoy",
        course="BS Psychology",
        gwa=Decimal("91.25"),
        year_level=1,
    ),
)
REJECT_REASON = "Your certificate of registration is from a school outside Taguig City University."

# rev 36: LANI applicants from three schools and scales, reviewed by the LANI staff account.
LANI_APPLICANTS: tuple[SampleApplicant, ...] = (
    SampleApplicant(
        "lani.applicant1@scholarsync.test",
        "Kristine",
        "Lim",
        date(2005, 10, 8),
        "submitted",
        barangay="central-bicutan",
        school="University of the Philippines",
        course="BS Psychology",
        gwa=Decimal("1.75"),
        tier="suc-lcu",
    ),
    SampleApplicant(
        "lani.applicant2@scholarsync.test",
        "Rafael",
        "Mercado",
        date(2006, 2, 14),
        "submitted",
        sex="male",
        barangay="calzada",
        school="University of Santo Tomas",
        course="BS Nursing",
        gwa=Decimal("2.75"),
        year_level=1,
        tier="basic",
    ),
    SampleApplicant(
        "lani.applicant3@scholarsync.test",
        "Mark",
        "Torres",
        date(2005, 5, 29),
        "under_review",
        sex="male",
        barangay="bambang",
        school="University of Santo Tomas",
        course="BS Architecture",
        gwa=Decimal("2.25"),
        year_level=3,
        tier="basic",
    ),
    SampleApplicant(
        "lani.applicant4@scholarsync.test",
        "Janelle",
        "Soriano",
        date(2006, 7, 3),
        "approved",
        barangay="katuparan",
        course="BS Accountancy",
        gwa=Decimal("92.00"),
        tier="priority",
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
    state: str  # due | low_gwa | on_hold


# TCU CEAA scholars from the previous semester. Carmela is due to renew; Daniel is due too, with
# a 78 under CEAA's 80% renewal mark; Elena's award is on hold. They share the demo
# password, so a visitor can sign in as Carmela and renew.
SAMPLE_SCHOLARS: tuple[SampleScholar, ...] = (
    SampleScholar(
        "scholar@scholarsync.test", "Carmela", "Villanueva", date(2005, 4, 18), Decimal("88"), "due"
    ),
    SampleScholar(
        "scholar2@scholarsync.test", "Daniel", "Ramos", date(2005, 9, 2), Decimal("78"), "low_gwa"
    ),
    SampleScholar(
        "scholar3@scholarsync.test", "Elena", "Garcia", date(2006, 1, 7), Decimal("85"), "on_hold"
    ),
)

HOLD_REASON = "Waiting for the registrar to confirm enrolment."


@dataclass(frozen=True)
class LaniScholar:
    email: str
    first_name: str
    last_name: str
    birth_date: date
    school: str
    school_type: str  # School.Type value
    gwa: Decimal  # last term's GWA on the 1-5 scale
    tier: str


# rev 36: LANI scholars from the previous semester, both due to renew. Joshua's 2.75 misses LANI's
# 2.50 renewal mark, so the LANI staff see both renewal states. They don't sign in.
LANI_SCHOLARS: tuple[LaniScholar, ...] = (
    LaniScholar(
        "lani.scholar1@scholarsync.test",
        "Andrea",
        "Salazar",
        date(2004, 12, 2),
        "University of the Philippines",
        "suc",
        Decimal("2.00"),
        "suc-lcu",
    ),
    LaniScholar(
        "lani.scholar2@scholarsync.test",
        "Joshua",
        "Valdez",
        date(2005, 3, 16),
        "University of Santo Tomas",
        "private",
        Decimal("2.75"),
        "basic",
    ),
)


@dataclass(frozen=True)
class ManualScholar:
    first_name: str
    last_name: str
    birth_date: date
    gwa: Decimal  # on TCU's percent scale


# A walk-in staff gave a TCU CEAA award by hand (M9b Add scholar): no account, never invited.
MANUAL_SCHOLAR = ManualScholar("Felipe", "Manalo", date(2005, 6, 18), Decimal("87.25"))


# Money samples (M10): TCU CEAA distribution days. The note marks the demo's schedules, so
# loading again adds nothing.
DEMO_CLAIM_LOCATION = "Taguig City University Gymnasium"
DEMO_SCHEDULE_NOTE = "Bring a valid ID."
DEMO_BUDGET = Decimal("1000000.00")
