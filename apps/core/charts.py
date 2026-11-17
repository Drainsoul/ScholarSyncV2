"""Month bars for the dashboards' CSS bar chart (heights in the 5 % steps the CSS maps)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MonthBar:
    label: str  # "October 2026"
    short: str  # "Oct"
    count: int
    percent: int  # 0-100 in steps of 5
    current: bool


def _shift(month: date, by: int) -> date:
    index = month.year * 12 + month.month - 1 + by
    return date(index // 12, index % 12 + 1, 1)


def first_month(today: date, months: int = 6) -> date:
    """The first day of the earliest month in a window that ends with today's month."""
    return _shift(today.replace(day=1), 1 - months)


def month_bars(counts: dict[date, int], *, today: date, months: int = 6) -> list[MonthBar]:
    """One bar per month ending with today's month; empty months are zero."""
    start = first_month(today, months)
    days = [_shift(start, n) for n in range(months)]
    values = [counts.get(day, 0) for day in days]
    peak = max(values)
    return [
        MonthBar(
            label=day.strftime("%B %Y"),
            short=day.strftime("%b"),
            count=value,
            percent=min(100, round(value / peak * 20) * 5) if peak else 0,
            current=index == months - 1,
        )
        for index, (day, value) in enumerate(zip(days, values, strict=True))
    ]
