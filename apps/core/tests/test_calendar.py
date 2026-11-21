"""The shared month grid and the day dialog's helpers (spec §12 rev 26/27/33)."""

from datetime import date

import pytest

from apps.core.calendar import CalendarDay, CalendarEvent, events_on, month_calendar
from apps.core.converters import IsoDateConverter

NOVEMBER = date(2026, 11, 1)
TODAY = date(2026, 11, 17)


def _event(day: date, title: str) -> CalendarEvent:
    return CalendarEvent(day, "opens", title, "")


def test_events_on_picks_the_day_by_title() -> None:
    day = date(2026, 11, 21)
    events = [
        _event(day, "Call the registrar"),
        _event(date(2026, 11, 22), "Another day"),
        _event(day, "Allowance release"),
    ]
    assert [e.title for e in events_on(day, events)] == ["Allowance release", "Call the registrar"]
    assert events_on(date(2026, 11, 1), events) == ()


def test_events_on_matches_the_grid_cell() -> None:
    day = date(2026, 12, 3)  # in the November grid's last week, outside the month
    events = [_event(day, "B"), _event(day, "A"), _event(date(2026, 11, 2), "C")]
    shown = month_calendar(NOVEMBER, today=TODAY, events=events)
    [cell] = [c for week in shown.weeks for c in week if c.day == day]
    assert not cell.in_month
    assert cell.events == events_on(day, events)


@pytest.mark.parametrize(
    ("count", "label"),
    [
        (0, "21 November 2026, no items"),
        (1, "21 November 2026, 1 item"),
        (2, "21 November 2026, 2 items"),
    ],
)
def test_a_cell_is_named_by_its_date_and_count(count: int, label: str) -> None:
    day = date(2026, 11, 21)
    cell = CalendarDay(day, True, False, tuple(_event(day, str(n)) for n in range(count)))
    assert cell.label == label


def test_every_cell_gets_its_day_url() -> None:
    shown = month_calendar(NOVEMBER, today=TODAY, events=[], day_url=lambda d: f"/d/{d}/")
    cells = [c for week in shown.weeks for c in week]
    assert all(c.url == f"/d/{c.day.isoformat()}/" for c in cells)
    assert month_calendar(NOVEMBER, today=TODAY, events=[]).weeks[0][0].url == ""


@pytest.mark.parametrize(
    "value", ["2026-02-30", "2026-13-01", "1999-12-31", "2101-01-01", "0001-01-01"]
)
def test_the_date_converter_rejects_impossible_dates(value: str) -> None:
    with pytest.raises(ValueError):
        IsoDateConverter().to_python(value)


def test_the_date_converter_round_trips() -> None:
    converter = IsoDateConverter()
    assert converter.to_python("2026-11-21") == date(2026, 11, 21)
    assert converter.to_url(date(2026, 11, 21)) == "2026-11-21"
    assert converter.to_url("2026-11-21") == "2026-11-21"
