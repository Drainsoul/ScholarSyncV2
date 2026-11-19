"""The student home's calendar (spec §12 rev 26)."""

from datetime import date, datetime
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award
from apps.awards.tests.factories import AwardFactory
from apps.matching.selectors import match_page
from apps.money.tests.factories import ScheduleFactory
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory
from apps.students.calendar import MonthCalendar, parse_month, student_calendar
from apps.students.tests.factories import (
    EducationRecordFactory,
    FullProfileFactory,
    ProfileFactory,
)

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=TZ)
TODAY = NOW.date()
NOVEMBER = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


@pytest.fixture
def term() -> Any:
    return AcademicTermFactory.create(school_year_start=2026, is_current=True)


def _calendar(user: User | None, month: date = NOVEMBER) -> MonthCalendar:
    assert user is not None
    return student_calendar(user, match_page(user, today=TODAY), today=TODAY, month=month)


def _titles(shown: MonthCalendar) -> list[str]:
    return [event.title for week in shown.weeks for day in week for event in day.events]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-12", date(2026, 12, 1)),
        ("2027-01", date(2027, 1, 1)),
        (None, NOVEMBER),
        ("", NOVEMBER),
        ("2026-13", NOVEMBER),
        ("2026-00", NOVEMBER),
        ("abcd-ef", NOVEMBER),
        ("1999-01", NOVEMBER),
        ("2026-1", NOVEMBER),
        ("2026/12", NOVEMBER),
    ],
)
def test_parse_month(value: str | None, expected: date) -> None:
    assert parse_month(value, today=TODAY) == expected


def test_grid_starts_on_monday_and_marks_today() -> None:
    shown = _calendar(ProfileFactory.create().user)
    assert shown.weeks[0][0].day.weekday() == 0
    assert all(len(week) == 7 for week in shown.weeks)
    today = [day for week in shown.weeks for day in week if day.is_today]
    assert [day.day for day in today] == [TODAY]
    assert shown.previous == "2026-10" and shown.following == "2026-12"
    assert shown.is_current_month


def test_december_steps_into_the_next_year() -> None:
    shown = _calendar(ProfileFactory.create().user, date(2026, 12, 1))
    assert shown.following == "2027-01" and not shown.is_current_month


def test_release_days_of_held_programs_only_when_published() -> None:
    award = AwardFactory.create(source_application__program=ProgramFactory.create(name="TCU CEAA"))
    user = award.profile.user
    ScheduleFactory.create(
        program=award.program, distribution_date=date(2026, 11, 28), claim_location="TCU Gym"
    )
    ScheduleFactory.create(
        program=award.program, distribution_date=date(2026, 11, 29), is_published=False
    )
    ScheduleFactory.create(program__name="Other Grant", distribution_date=date(2026, 11, 27))
    shown = _calendar(user)
    assert _titles(shown) == ["TCU CEAA allowance release"]
    assert [(e.title, e.detail) for e in shown.upcoming] == [
        ("TCU CEAA allowance release", "TCU Gym")
    ]


def test_no_release_days_after_the_award_ends() -> None:
    award = AwardFactory.create(status=Award.Status.INACTIVE)
    ScheduleFactory.create(program=award.program, distribution_date=date(2026, 11, 28))
    assert _titles(_calendar(award.profile.user)) == []


def test_window_of_a_program_with_an_unfinished_application(term: Any) -> None:
    program = ProgramFactory.create(
        name="LANI",
        applications_open_on=date(2026, 11, 2),
        applications_close_on=date(2026, 11, 30),
    )
    profile = ProfileFactory.create()
    ApplicationFactory.create(profile=profile, program=program, term=term)
    titles = _titles(_calendar(profile.user))
    assert titles == ["LANI applications open", "LANI applications close"]


def test_window_of_a_program_the_student_qualifies_for_even_before_it_opens(term: Any) -> None:
    ProgramFactory.create(
        name="Youth Grant",
        applications_open_on=date(2026, 12, 7),
        applications_close_on=date(2027, 1, 15),
    )
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    shown = _calendar(profile.user, date(2026, 12, 1))
    assert _titles(shown) == ["Youth Grant applications open"]
    assert [e.title for e in shown.upcoming] == [
        "Youth Grant applications open",
        "Youth Grant applications close",
    ]


def test_no_window_for_a_program_the_student_does_not_qualify_for(term: Any) -> None:
    ProgramFactory.create(applications_open_on=date(2026, 11, 2))
    profile = FullProfileFactory.create()  # no current school: fails a rule
    assert _titles(_calendar(profile.user)) == []


def test_upcoming_is_sorted_and_capped_at_five(term: Any) -> None:
    award = AwardFactory.create()
    for day in (30, 25, 22, 21, 26, 29, 23):
        ScheduleFactory.create(program=award.program, distribution_date=date(2026, 11, day))
    ScheduleFactory.create(program=award.program, distribution_date=date(2026, 11, 19))
    upcoming = _calendar(award.profile.user).upcoming
    assert [e.day.day for e in upcoming] == [21, 22, 23, 25, 26]


def _signed_in(client: Any) -> User:
    user = ProfileFactory.create().user
    assert user is not None
    client.force_login(user)
    return user


def test_home_shows_the_calendar_and_ring(client: Any, vite_build: Any) -> None:
    _signed_in(client)
    html = client.get(reverse("students:home")).content.decode()
    assert 'id="home-calendar"' in html
    assert "November 2026" in html
    assert 'aria-current="date"' in html
    assert 'stroke-dasharray="' in html and 'pathLength="100"' in html
    assert "<progress" not in html
    assert "Coming up" in html


def test_home_with_a_bad_month_falls_back_to_this_month(client: Any, vite_build: Any) -> None:
    _signed_in(client)
    response = client.get(reverse("students:home"), {"month": "2026-99"})
    assert response.status_code == 200
    assert "November 2026" in response.content.decode()


def test_month_step_returns_only_the_calendar(client: Any, vite_build: Any) -> None:
    _signed_in(client)
    response = client.get(
        reverse("students:home"),
        {"month": "2026-12"},
        headers={"HX-Request": "true", "HX-Target": "home-calendar"},
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "December 2026" in html
    assert "sidebar" not in html and "Coming up" not in html
    assert "HX-Target" in response["Vary"]
