from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.files.policy import MB
from apps.programs.rules import rule_sentences
from apps.programs.selectors import required_documents_for, tiers_in_force
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)


def test_latest_effective_tier_wins_and_future_rows_wait(db):
    p = ProgramFactory.create()
    t1, t2, t3 = (AcademicTermFactory.create(school_year_start=2026, term=n) for n in (1, 2, 3))
    BenefitTierFactory.create(
        program=p, code="basic", base_amount=Decimal("7500.00"), effective_from=t1
    )
    BenefitTierFactory.create(
        program=p, code="basic", base_amount=Decimal("8000.00"), effective_from=t2
    )
    BenefitTierFactory.create(program=p, code="lead", effective_from=t3)
    assert [(t.code, t.base_amount) for t in tiers_in_force(p, t2)] == [
        ("basic", Decimal("8000.00"))
    ]
    assert [t.base_amount for t in tiers_in_force(p, t1)] == [Decimal("7500.00")]


def test_inactive_row_ends_the_tier(db):
    p = ProgramFactory.create()
    t1, t2 = (AcademicTermFactory.create(school_year_start=2026, term=n) for n in (1, 2))
    first = BenefitTierFactory.create(program=p, code="lead", effective_from=t1)
    BenefitTierFactory.create(program=p, code="lead", effective_from=t2, is_active=False)
    assert tiers_in_force(p, t2) == []
    assert tiers_in_force(p, t1) == [first]


def test_tiers_are_ordered_by_sort_order_then_name(db):
    p = ProgramFactory.create()
    t1 = AcademicTermFactory.create(school_year_start=2026, term=1)
    b = BenefitTierFactory.create(program=p, code="b", name="B", sort_order=1, effective_from=t1)
    a = BenefitTierFactory.create(program=p, code="a", name="A", sort_order=1, effective_from=t1)
    z = BenefitTierFactory.create(program=p, code="z", name="Z", sort_order=0, effective_from=t1)
    assert tiers_in_force(p, t1) == [z, a, b]


def test_tier_is_unique_per_program_code_and_term(db):
    p = ProgramFactory.create()
    t1 = AcademicTermFactory.create(school_year_start=2026, term=1)
    BenefitTierFactory.create(program=p, code="basic", effective_from=t1)
    with pytest.raises(IntegrityError), transaction.atomic():
        BenefitTierFactory.create(program=p, code="basic", effective_from=t1)


@pytest.mark.parametrize(
    "kwargs", [{"base_amount": Decimal("-1.00")}, {"merit_amount": Decimal("-0.01")}]
)
def test_tier_amounts_cannot_be_negative(db, kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        BenefitTierFactory.create(**kwargs)


def test_required_documents_by_kind(db):
    p = ProgramFactory.create()
    new, ren, both = (
        RequiredDocumentFactory.create(program=p, applies_to=a) for a in ("new", "renewal", "both")
    )
    assert set(required_documents_for(p, "new")) == {new, both}
    assert set(required_documents_for(p, "renewal")) == {ren, both}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"accepted_types": ["application/zip"]},
        {"accepted_types": []},
        {"max_bytes": 10 * MB + 1},
        {"max_bytes": 0},
        {"applies_to": "nobody"},
    ],
)
def test_document_limits_stay_inside_the_upload_rule(db, kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        RequiredDocumentFactory.create(**kwargs)


def test_document_defaults_match_the_upload_rule(db):
    doc = RequiredDocumentFactory.create()
    assert doc.accepted_types == ["application/pdf", "image/jpeg", "image/png"]
    assert doc.max_bytes == 10 * MB


def test_document_code_is_unique_per_program(db):
    p = ProgramFactory.create()
    RequiredDocumentFactory.create(program=p, code="cor")
    with pytest.raises(IntegrityError), transaction.atomic():
        RequiredDocumentFactory.create(program=p, code="cor")


def test_window_must_open_before_it_closes(db):
    ProgramFactory.create(
        applications_open_on=date(2026, 6, 1), applications_close_on=date(2026, 6, 1)
    )
    ProgramFactory.create(applications_open_on=date(2026, 6, 1))
    ProgramFactory.create(applications_close_on=date(2026, 6, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        ProgramFactory.create(
            applications_open_on=date(2026, 6, 2), applications_close_on=date(2026, 6, 1)
        )


def test_rule_sentences(db):
    tcu = SchoolFactory.create(name="Taguig City University")
    p = ProgramFactory.create(
        min_gwa_percent=Decimal("80.00"), min_residency_years=1, requires_registered_voter=True
    )
    p.allowed_schools.add(tcu)
    assert rule_sentences(p) == [
        "A GWA of at least 80% (schools that grade in percent).",
        "Living in Taguig for at least 1 year.",
        "A registered voter of Taguig.",
        "Studying at Taguig City University.",
    ]
    assert rule_sentences(ProgramFactory.create()) == []


def test_rule_sentences_for_the_other_rules(db):
    a, b = SchoolFactory.create(name="A College"), SchoolFactory.create(name="B College")
    p = ProgramFactory.create(
        max_gwa_one_to_five=Decimal("2.50"),
        min_units=15,
        min_residency_years=3,
        allowed_school_types=["public", "lcu"],
    )
    p.allowed_schools.add(a, b)
    assert rule_sentences(p) == [
        "A GWA of 2.50 or better (schools that grade 1 to 5).",
        "At least 15 units this term.",
        "Living in Taguig for at least 3 years.",
        "Studying at A College or B College.",
        "Studying at a public school or local college or university.",
    ]


def test_tiers_in_force_query_count(db, django_assert_max_num_queries):
    p = ProgramFactory.create()
    term = AcademicTermFactory.create(school_year_start=2026, term=1)
    for n in range(10):
        BenefitTierFactory.create(program=p, code=f"t{n}", effective_from=term)
    with django_assert_max_num_queries(1):
        assert len(tiers_in_force(p, term)) == 10


def test_database_refuses_unknown_allowed_school_types(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        ProgramFactory.create(allowed_school_types=["public", "academy"])
    ProgramFactory.create(allowed_school_types=["public", "lcu"])


def test_school_type_wording() -> None:
    from apps.programs.rules import rule_sentence

    program = ProgramFactory.build(allowed_school_types=["lcu"])
    assert rule_sentence(program, "school_type") == "Studying at a local college or university."
