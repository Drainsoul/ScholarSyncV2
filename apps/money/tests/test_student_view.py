from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.awards.models import Award
from apps.awards.tests.factories import ScholarTermFactory
from apps.money import selectors
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.programs.models import AcademicTerm
from apps.programs.tests.factories import AcademicTermFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 1)
TZ = timezone.get_default_timezone()


@pytest.fixture
def terms() -> tuple[AcademicTerm, AcademicTerm]:
    """Last school year's 2nd semester and this school year's (current) 1st semester."""
    last = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    return last, current


def _user(row: Disbursement) -> User:
    user = row.scholar_term.award.profile.user
    assert user is not None
    return user


def _more(row: Disbursement, term: AcademicTerm, **kwargs: Any) -> Disbursement:
    """Another payout of the same award, in a new schedule of `term`."""
    award = row.scholar_term.award
    record = ScholarTermFactory.create(award=award, term=term)
    schedule = ScheduleFactory.create(
        program=award.program, term=term, distribution_date=kwargs.pop("day", TODAY)
    )
    return DisbursementFactory.create(scholar_term=record, schedule=schedule, **kwargs)


def _first(term: AcademicTerm, **kwargs: Any) -> Disbursement:
    schedule = ScheduleFactory.create(
        term=term,
        distribution_date=kwargs.pop("day", TODAY),
        is_published=kwargs.pop("is_published", True),
    )
    return payout(schedule, **kwargs)


def test_figures(terms: Any) -> None:
    last, current = terms
    received = _first(last, status=Disbursement.Status.RELEASED, day=date(2026, 3, 1))
    received.released_at = datetime(2026, 3, 2, 10, tzinfo=TZ)
    received.save()
    award = received.scholar_term.award
    second = ScholarTermFactory.create(award=award, term=current)
    approved_schedule = ScheduleFactory.create(program=award.program, term=current)
    DisbursementFactory.create(
        scholar_term=second,
        schedule=approved_schedule,
        status=Disbursement.Status.APPROVED,
        amount=Decimal("10000.00"),
    )
    found = selectors.payouts_for_student(_user(received), today=TODAY)[award.pk]
    assert found.times_claimed == 1
    assert found.received == Decimal("5000.00")
    assert found.to_come == Decimal("10000.00")
    assert [row.status for row in found.rows] == ["approved", "released"]


def test_last_years_pending_is_not_to_come(terms: Any) -> None:
    last, _ = terms
    row = _first(last)
    found = selectors.payouts_for_student(_user(row), today=TODAY)
    assert found[row.scholar_term.award_id].to_come == Decimal("0")


def test_unpublished_schedule_rows_are_hidden(terms: Any) -> None:
    _, current = terms
    row = _first(current, is_published=False)
    found = selectors.payouts_for_student(_user(row), today=TODAY)
    assert found[row.scholar_term.award_id].rows == []


def test_other_students_rows_are_never_shown(terms: Any) -> None:
    _, current = terms
    mine = _first(current)
    theirs = _first(current)
    found = selectors.payouts_for_student(_user(mine), today=TODAY)
    assert theirs.scholar_term.award_id not in found
    assert [row.pk for row in found[mine.scholar_term.award_id].rows] == [mine.pk]


def test_next_distribution_is_the_earliest_upcoming_published(terms: Any) -> None:
    _, current = terms
    row = _first(current, day=date(2026, 9, 1))  # past
    program = row.schedule.program
    ScheduleFactory.create(
        program=program, term=current, distribution_date=date(2026, 10, 5), is_published=False
    )
    later = ScheduleFactory.create(
        program=program, term=current, distribution_date=date(2026, 11, 20)
    )
    sooner = ScheduleFactory.create(
        program=program,
        term=current,
        distribution_date=date(2026, 10, 15),
        claim_location="City Hall",
        notes="Bring a valid ID.",
    )
    ScheduleFactory.create(  # a term the award has no record in
        program=program, term=AcademicTermFactory.create(), distribution_date=date(2026, 10, 2)
    )
    found = selectors.payouts_for_student(_user(row), today=TODAY)
    assert found[row.scholar_term.award_id].next_schedule == sooner
    assert later.pk != sooner.pk


def test_page_shows_payouts(client: Any, terms: Any, time_machine: Any) -> None:
    time_machine.move_to(datetime(2026, 10, 1, 9, tzinfo=TZ), tick=False)
    last, current = terms
    released = _first(last, status=Disbursement.Status.RELEASED, day=date(2026, 3, 1))
    released.released_at = datetime(2026, 3, 2, 10, tzinfo=TZ)
    released.save()
    award = released.scholar_term.award
    _more(
        released,
        current,
        status=Disbursement.Status.REJECTED,
        decision_reason="No ID shown.",
        day=date(2026, 9, 1),
    )
    _more(
        released, AcademicTermFactory.create(school_year_start=2026, term=2), day=date(2026, 9, 2)
    )
    upcoming = ScheduleFactory.create(
        program=award.program,
        term=current,
        distribution_date=date(2026, 10, 15),
        claim_location="City Hall",
    )
    assert upcoming.pk
    client.force_login(_user(released))
    html = client.get(reverse("scholarships:list")).content.decode()
    for text in (
        "Times claimed",
        "Total received",
        "Still to come this school year",
        "Next distribution",
        "15 October 2026",
        "City Hall",
        "Received 2 March 2026",
        "Not paid",
        "No ID shown.",
        "Being prepared",
    ):
        assert text in html, text


def test_page_without_payouts(client: Any, terms: Any) -> None:
    _, current = terms
    row = _first(current)
    Disbursement.objects.filter(pk=row.pk).delete()
    client.force_login(_user(row))
    assert "No payouts yet." in client.get(reverse("scholarships:list")).content.decode()


def test_scholarships_query_count(
    client: Any, terms: Any, django_assert_max_num_queries: Any
) -> None:
    _, current = terms
    first = _first(current)
    user = _user(first)
    profile = first.scholar_term.award.profile
    for _ in range(2):
        other = _first(current)
        award = other.scholar_term.award
        Award.objects.filter(pk=award.pk).update(profile=profile)
    for award in Award.objects.filter(profile=profile):
        for number in range(10):
            term = AcademicTermFactory.create()
            record = ScholarTermFactory.create(award=award, term=term)
            schedule = ScheduleFactory.create(program=award.program, term=term)
            DisbursementFactory.create(scholar_term=record, schedule=schedule)
            assert number >= 0
    client.force_login(user)
    with django_assert_max_num_queries(25):
        assert client.get(reverse("scholarships:list")).status_code == 200


def test_still_to_come_skips_awards_not_active(terms: Any) -> None:
    _, current = terms
    row = _first(current, status=Disbursement.Status.APPROVED)
    Award.objects.filter(pk=row.scholar_term.award_id).update(status=Award.Status.SUSPENDED)
    found = selectors.payouts_for_student(_user(row), today=TODAY)
    assert found[row.scholar_term.award_id].to_come == Decimal("0")
