"""Parsing request parameters that name rows."""

MAX_ID = 2**31 - 1  # Postgres integer primary keys


def positive_id(raw: str) -> int | None:
    """The row id in `raw`, or None for anything that is not a plausible id (never raises)."""
    if not raw.isascii() or not raw.isdigit():
        return None
    value = int(raw)
    return value if 0 < value <= MAX_ID else None
