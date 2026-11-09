from datetime import date, timedelta

import pytest

from apps.programs.selectors import application_term, window_state
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory

TODAY = date(2026, 11, 10)


def test_application_term_prefers_the_flagged_term(db):
    flagged = AcademicTermFactory.create(
        school_year_start=2030,
        starts_on=date(2030, 8, 1),
        ends_on=date(2030, 12, 1),
        is_current=True,
    )
    AcademicTermFactory.create(
        school_year_start=2026, starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 20)
    )
    assert application_term(TODAY) == flagged


def test_application_term_falls_back_to_the_dated_term(db):
    AcademicTermFactory.create(
        school_year_start=2020, starts_on=date(2020, 8, 1), ends_on=date(2020, 12, 1)
    )
    dated = AcademicTermFactory.create(
        school_year_start=2026, starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 20)
    )
    assert application_term(TODAY) == dated


def test_application_term_none_without_terms(db):
    assert application_term(TODAY) is None


@pytest.mark.parametrize(
    ("opens", "closes", "expected"),
    [
        (None, None, "open"),
        (TODAY + timedelta(days=1), None, "not_yet"),
        (None, TODAY - timedelta(days=1), "closed"),
        (TODAY, TODAY, "open"),
    ],
)
def test_window_state(db, opens, closes, expected):
    program = ProgramFactory.create(applications_open_on=opens, applications_close_on=closes)
    assert window_state(program, TODAY) == expected
