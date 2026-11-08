from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.programs.models import AcademicTerm
from apps.programs.terms import school_year_terms
from apps.programs.tests.factories import AcademicTermFactory, SchoolFactory


@pytest.mark.parametrize(
    "today,start",
    [(date(2026, 8, 1), 2026), (date(2027, 7, 31), 2026), (date(2026, 7, 31), 2025)],
)
def test_school_year_starts_in_august(today: date, start: int) -> None:
    terms = school_year_terms(today)
    assert [t.term for t in terms] == [1, 2, 3]
    assert {t.school_year_start for t in terms} == {start}
    assert terms[0].starts_on == date(start, 8, 1)
    assert terms[0].ends_on == date(start, 12, 31)
    assert terms[1].starts_on == date(start + 1, 1, 1)
    assert terms[1].ends_on == date(start + 1, 5, 31)
    assert terms[2].starts_on == date(start + 1, 6, 1)
    assert terms[2].ends_on == date(start + 1, 7, 31)


def test_only_one_current_term(db: None) -> None:
    AcademicTermFactory.create(is_current=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicTermFactory.create(is_current=True)


def test_many_terms_may_be_not_current(db: None) -> None:
    AcademicTermFactory.create()
    AcademicTermFactory.create()
    assert AcademicTerm.objects.filter(is_current=False).count() == 2


def test_sort_key_orders_summer_before_next_year(db: None) -> None:
    b = AcademicTermFactory.create(school_year_start=2027, term=1)
    a = AcademicTermFactory.create(school_year_start=2026, term=3)
    assert list(AcademicTerm.objects.values_list("pk", flat=True)) == [a.pk, b.pk]


def test_term_label(db: None) -> None:
    term = AcademicTermFactory.create(school_year_start=2026, term=3)
    assert str(term) == "Summer, SY 2026–2027"
    assert str(AcademicTermFactory.create(school_year_start=2026, term=1)) == (
        "1st semester, SY 2026–2027"
    )


def test_term_unique_per_school_year(db: None) -> None:
    AcademicTermFactory.create(school_year_start=2026, term=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicTermFactory.create(school_year_start=2026, term=1)


def test_term_value_must_be_valid(db: None) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicTermFactory.create(term=4, starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 31))


def test_school_names_unique_ignoring_case(db: None) -> None:
    SchoolFactory.create(name="Taguig City University")
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolFactory.create(name="taguig city university")


def test_school_type_and_scale_must_be_valid(db: None) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolFactory.create(type="academy")
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolFactory.create(grading_scale="letter")


def test_end_must_follow_start(db: None) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicTermFactory.create(starts_on=date(2026, 8, 1), ends_on=date(2026, 8, 1))
