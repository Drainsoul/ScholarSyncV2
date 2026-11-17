from datetime import date

from apps.core.charts import first_month, month_bars


def test_six_months_zero_filled_ending_this_month() -> None:
    bars = month_bars({date(2026, 9, 1): 4, date(2026, 11, 1): 8}, today=date(2026, 11, 17))
    assert [bar.short for bar in bars] == ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
    assert [bar.count for bar in bars] == [0, 0, 0, 4, 0, 8]
    assert bars[-1].label == "November 2026"
    assert [bar.current for bar in bars] == [False] * 5 + [True]


def test_percent_steps_of_five_and_all_zero_peak() -> None:
    bars = month_bars({date(2026, 10, 1): 3, date(2026, 11, 1): 7}, today=date(2026, 11, 2))
    assert bars[-1].percent == 100
    assert bars[-2].percent == 45  # 3/7 = 42.9 % → 45
    assert all(bar.percent % 5 == 0 for bar in bars)
    assert all(bar.percent == 0 for bar in month_bars({}, today=date(2026, 11, 2)))


def test_window_crosses_the_year() -> None:
    bars = month_bars({}, today=date(2027, 2, 10))
    assert [bar.label for bar in bars] == [
        "September 2026",
        "October 2026",
        "November 2026",
        "December 2026",
        "January 2027",
        "February 2027",
    ]
    assert first_month(date(2027, 2, 10)) == date(2026, 9, 1)
