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
