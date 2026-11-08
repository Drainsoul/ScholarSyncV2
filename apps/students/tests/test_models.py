from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import ProgramFactory
from apps.students import barangays
from apps.students.models import FamilyMember, StudentProfile
from apps.students.tests.factories import (
    EducationRecordFactory,
    FamilyMemberFactory,
    ProfileFactory,
)


def test_one_profile_per_user(db):
    p = ProfileFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        ProfileFactory.create(user=p.user)


def test_profile_without_user_is_allowed(db):
    ProfileFactory.create(user=None)
    ProfileFactory.create(user=None)


def test_full_name_keeps_filipino_spelling():
    p = ProfileFactory.build(
        first_name="Ma. Niña", middle_name="", last_name="Dela Cruz-Santos", suffix="Jr."
    )
    assert p.full_name == "Ma. Niña Dela Cruz-Santos Jr."


def test_full_name_with_middle_name():
    p = ProfileFactory.build(first_name="Ana", middle_name="Reyes", last_name="Cruz", suffix="")
    assert p.full_name == "Ana Reyes Cruz"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sex": "other"},
        {"barangay": "makati"},
        {"monthly_household_income": Decimal("-1")},
    ],
)
def test_profile_constraints(db, kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        ProfileFactory.create(**kwargs)


def test_profile_accepts_blank_and_valid_choices(db):
    ProfileFactory.create(sex="", barangay="")
    ProfileFactory.create(sex="male", barangay="outside-taguig")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"relation": "cousin"},
        {"monthly_income": Decimal("-0.01")},
    ],
)
def test_family_constraints(db, kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        FamilyMemberFactory.create(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"school": None, "school_name": ""},
        {"school_name": "Also named"},  # both set
        {"gwa": Decimal("95.00"), "gwa_scale": "one_to_five"},
        {
            "gwa": Decimal("1.25"),
            "gwa_scale": "percent",
            "school": None,
            "school_name": "Ususan HS",
            "school_type": "public",
        },
        {"gwa": Decimal("2.00"), "gwa_scale": ""},
        {"gwa": Decimal("4.50"), "gwa_scale": "four_point"},
        {"year_from": 2026, "year_to": 2024},
        {"level": "kindergarten"},
    ],
)
def test_education_constraints(db, kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        EducationRecordFactory.create(**kwargs)


def test_education_valid_fallback_school_name_and_grades(db):
    EducationRecordFactory.create(
        school=None,
        school_name="Ususan High School",
        school_type="public",
        level="jhs",
        gwa=Decimal("92.50"),
        gwa_scale="percent",
        year_from=2018,
        year_to=2022,
    )
    EducationRecordFactory.create(gwa=Decimal("1.25"), gwa_scale="one_to_five")
    EducationRecordFactory.create(gwa=Decimal("3.75"), gwa_scale="four_point")


def test_photo_set_null_when_file_deleted(db):
    f = StoredFileFactory.create(
        purpose="photo", status="ready", sha256="x" * 64, sniffed_type="image/png"
    )
    p = ProfileFactory.create(photo=f)
    f.delete()
    p.refresh_from_db()
    assert p.photo is None


def test_created_for_set_null_when_program_deleted(db):
    program = ProgramFactory.create()
    p = ProfileFactory.create(created_for=program)
    program.delete()
    p.refresh_from_db()
    assert p.created_for is None


def test_barangays_list():
    values = [v for v, _ in barangays.BARANGAYS]
    assert len(barangays.TAGUIG_BARANGAYS) == 38
    assert "pembo" in barangays.TAGUIG_BARANGAYS
    assert "west-rembo" in barangays.TAGUIG_BARANGAYS
    assert "outside-taguig" not in barangays.TAGUIG_BARANGAYS
    assert values[-1] == "outside-taguig"
    assert barangays.BARANGAYS[-1][1] == "I don't live in Taguig"
    assert values[:-1] == sorted(values[:-1])
    assert len(set(values)) == 39
    assert "ususan" in values
    assert "ibayo-tipas" in values


def test_choices_enums():
    assert StudentProfile.Sex.values == ["female", "male"]
    assert FamilyMember.Relation.values == ["father", "mother", "guardian", "sibling"]


def test_birth_date_nullable(db):
    p = ProfileFactory.create(birth_date=date(2006, 3, 14))
    assert p.birth_date == date(2006, 3, 14)
