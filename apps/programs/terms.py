from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TermSpec:
    school_year_start: int
    term: int
    starts_on: date
    ends_on: date


def school_year_terms(today: date) -> list[TermSpec]:
    """The three terms of the school year containing ``today`` (a year starts 1 August)."""
    start = today.year if today.month >= 8 else today.year - 1
    return [
        TermSpec(start, 1, date(start, 8, 1), date(start, 12, 31)),
        TermSpec(start, 2, date(start + 1, 1, 1), date(start + 1, 5, 31)),
        TermSpec(start, 3, date(start + 1, 6, 1), date(start + 1, 7, 31)),
    ]
