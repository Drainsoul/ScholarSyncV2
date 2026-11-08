from decimal import Decimal

from apps.files.tests.factories import StoredFileFactory
from apps.students.completion import completion
from apps.students.tests.factories import (
    EducationRecordFactory,
    FamilyMemberFactory,
    FullProfileFactory,
    ProfileFactory,
)


def test_empty_profile_is_zero_and_full_is_100(db):
    p = ProfileFactory.create(first_name="", last_name="")
    c = completion(p, family=[], education=[])
    assert c.percent == 0
    assert [s.done for s in c.sections] == [False] * 4
    assert [s.key for s in c.sections] == ["personal", "family", "education", "photo"]
    assert [s.label for s in c.sections] == ["Personal details", "Family", "Education", "Photo"]
    assert [s.url_name for s in c.sections] == [
        "students:profile-personal",
        "students:profile-family",
        "students:profile-education",
        "students:profile-photo",
    ]
    full = FullProfileFactory.create(
        photo=StoredFileFactory.create(status="ready", sha256="x" * 64, sniffed_type="image/png")
    )
    c = completion(
        full,
        family=[FamilyMemberFactory.build(relation="mother")],
        education=[EducationRecordFactory.build(is_current=True)],
    )
    assert c.percent == 100
    assert all(s.done for s in c.sections)


def test_missing_items_use_verbose_names(db):
    c = completion(ProfileFactory.create(), family=[], education=[])
    assert c.sections[0].missing == (
        "birth date",
        "sex",
        "phone",
        "address",
        "barangay",
        "residing since",
        "registered voter",
        "household income",
    )
    assert c.sections[1].missing == ("a parent or guardian",)
    assert c.sections[2].missing == ("your current school",)
    assert c.sections[3].missing == ("a photo",)
    assert c.percent == 2 * 100 // 13


def test_blank_names_are_missing(db):
    p = ProfileFactory.create(first_name="", last_name="")
    assert completion(p, family=[], education=[]).sections[0].missing[:2] == (
        "first name",
        "last name",
    )


def test_sibling_alone_does_not_complete_family(db):
    c = completion(
        FullProfileFactory.create(),
        family=[FamilyMemberFactory.build(relation="sibling")],
        education=[],
    )
    assert c.sections[1].missing == ("a parent or guardian",)
    assert c.percent == 10 * 100 // 13  # 76


def test_non_current_education_does_not_count(db):
    c = completion(
        ProfileFactory.create(),
        family=[],
        education=[EducationRecordFactory.build(is_current=False)],
    )
    assert c.sections[2].missing == ("your current school",)


def test_false_voter_answer_counts_as_answered(db):
    c = completion(FullProfileFactory.create(is_registered_voter=False), family=[], education=[])
    assert "registered voter" not in c.sections[0].missing
    c = completion(FullProfileFactory.create(is_registered_voter=None), family=[], education=[])
    assert "registered voter" in c.sections[0].missing


def test_zero_income_counts_as_answered(db):
    c = completion(
        FullProfileFactory.create(monthly_household_income=Decimal("0")), family=[], education=[]
    )
    assert c.sections[0].done
