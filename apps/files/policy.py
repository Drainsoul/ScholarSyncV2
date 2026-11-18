"""Upload rules: which types, sizes and roles each purpose accepts."""

from collections.abc import Iterable
from dataclasses import dataclass

from apps.accounts.models import User

MB = 1024 * 1024

STARTS_PER_HOUR = 20
STAFF_STARTS_PER_HOUR = 100
SNIFF_BYTES = 4096
MAX_IMAGE_PIXELS = 40_000_000

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"
CSV = "text/csv"
CSV_EXCEL = "application/vnd.ms-excel"  # what Windows browsers with Excel declare for .csv
CSV_TEXT = "text/plain"  # what some browsers declare for .csv; the sniff still refuses binaries
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

EXTENSIONS: dict[str, tuple[str, ...]] = {
    PDF: (".pdf",),
    JPEG: (".jpg", ".jpeg"),
    PNG: (".png",),
    CSV: (".csv",),
    CSV_EXCEL: (".csv",),
    CSV_TEXT: (".csv",),
    XLSX: (".xlsx",),
}

_LABELS = {
    PDF: "PDF",
    JPEG: "JPG",
    PNG: "PNG",
    CSV: "CSV",
    CSV_EXCEL: "CSV",
    CSV_TEXT: "CSV",
    XLSX: "XLSX",
}

_CANONICAL = {CSV_EXCEL: CSV, CSV_TEXT: CSV}

_ALL_ROLES = frozenset({User.Role.STUDENT, User.Role.STAFF, User.Role.SUPER_ADMIN})


@dataclass(frozen=True)
class PurposeRule:
    types: tuple[str, ...]
    max_bytes: int
    roles: frozenset[str]


RULES: dict[str, PurposeRule] = {
    "document": PurposeRule(types=(PDF, JPEG, PNG), max_bytes=10 * MB, roles=_ALL_ROLES),
    "photo": PurposeRule(types=(JPEG, PNG), max_bytes=5 * MB, roles=_ALL_ROLES),
    "report": PurposeRule(
        types=(PDF,),
        max_bytes=20 * MB,
        roles=frozenset({User.Role.STAFF, User.Role.SUPER_ADMIN}),
    ),
    "import": PurposeRule(
        types=(CSV, CSV_EXCEL, CSV_TEXT, XLSX),
        max_bytes=2 * MB,
        roles=frozenset({User.Role.STAFF, User.Role.SUPER_ADMIN}),
    ),
}


def canonical_type(declared: str) -> str:
    """The type a declared type is checked as: Excel's CSV type is plain CSV."""
    return _CANONICAL.get(declared, declared)


def types_phrase(purpose: str) -> str:
    """The accepted types in words, such as "PDF, JPG or PNG"."""
    return join_types(RULES[purpose].types)


def join_types(types: Iterable[str]) -> str:
    """Known types in words, always in PDF, JPG, PNG order: ("image/png", PDF) is "PDF or PNG".

    Types sharing a label (both CSV types) are named once."""
    wanted = set(types)
    labels = list(dict.fromkeys(label for mime, label in _LABELS.items() if mime in wanted))
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} or {labels[-1]}"


def help_text(purpose: str) -> str:
    return f"{types_phrase(purpose)}, up to {RULES[purpose].max_bytes // MB} MB."
