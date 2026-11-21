"""URL path converters, registered in `CoreConfig.ready`."""

from datetime import date

# As `?month=` (core/calendar.py): a year outside this is no date.
MIN_YEAR, MAX_YEAR = 2000, 2100


class IsoDateConverter:
    """`<isodate:day>`: a real `YYYY-MM-DD` date; anything else (2026-02-30, year 1999) is a 404."""

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        day = date.fromisoformat(value)
        if not MIN_YEAR <= day.year <= MAX_YEAR:
            raise ValueError(value)
        return day

    def to_url(self, value: date | str) -> str:
        return value.isoformat() if isinstance(value, date) else value
