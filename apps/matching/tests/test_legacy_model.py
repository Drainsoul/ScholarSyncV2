import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.matching import legacy_model
from apps.matching.eligibility import Academic
from apps.matching.legacy_model import (
    Hint,
    grade_from_percent,
    hint_for,
    predict_proba,
    suggest,
)
from apps.programs.models import School
from apps.students.tests.factories import ProfileFactory

PARITY = Path(__file__).parent / "data" / "legacy_parity.json"


def academic(**overrides: object) -> Academic:
    values: dict[str, object] = {
        "school": None,
        "school_name": "Taguig City University",
        "school_type": "public",
        "gwa_scale": School.Scale.PERCENT,
        "gwa": Decimal("90"),
        "units": 18,
        "course": "BSIT",
        "year_level": 2,
    }
    values.update(overrides)
    return Academic(**values)  # type: ignore[arg-type]


def test_parity_with_sklearn() -> None:
    rows = json.loads(PARITY.read_text(encoding="utf-8"))
    assert len(rows) >= 30
    for row in rows:
        got = predict_proba(
            grade=row["grade"],
            income=row["income"],
            school_name=row["school_name"],
            school_type=row["school_type"],
        )
        assert len(got) == len(row["proba"])
        for a, b in zip(got, row["proba"], strict=True):
            assert a == pytest.approx(b, abs=1e-9)


def test_grade_from_percent_matches_v1() -> None:
    assert grade_from_percent(Decimal("70")) == 1.0
    assert grade_from_percent(Decimal("85")) == 2.5
    assert grade_from_percent(Decimal("100")) == 4.0
    assert grade_from_percent(Decimal("50")) == 1.0
    # Mirrors v1's float rounding: 88.55 computes as 2.8549999..., so 2.85.
    assert grade_from_percent(Decimal("88.55")) == 2.85


def test_unknown_school_encodes_as_zeros() -> None:
    def run(name: str) -> list[float]:
        return predict_proba(grade=2.0, income=20000.0, school_name=name, school_type="public")

    assert run("Nowhere College") == run("")


def test_unknown_mode_raises() -> None:
    model = dict(legacy_model._load())
    model["proba"] = "bogus"
    with pytest.raises(ValueError):
        legacy_model._validate(model)


def test_suggest_maps_class_to_program_and_merit() -> None:
    for grade_pct, income, name, kind in [
        ("99", "5000", "Taguig City University", "public"),
        ("72", "90000", "University of Santo Tomas", "private"),
        ("85", "30000", "University of the Philippines", "public"),
    ]:
        hint = suggest(
            gwa_percent=Decimal(grade_pct),
            income=Decimal(income),
            school_name=name,
            school_type=kind,
        )
        label = hint.label
        assert isinstance(hint, Hint)
        assert 0 <= hint.probability <= 1
        assert hint.merit is label.endswith("_Merit")
        if label.startswith("CEAA_"):
            assert hint.program_slug == "tcu-ceaa"
        elif label.startswith("LANI_"):
            assert hint.program_slug == "lani"
        else:
            assert label == "NotEligible"
            assert hint.program_slug is None


def test_map_helpers() -> None:
    assert legacy_model._program_for("CEAA_Merit") == "tcu-ceaa"
    assert legacy_model._program_for("LANI_Basic") == "lani"
    assert legacy_model._program_for("NotEligible") is None


@pytest.mark.django_db
def test_hint_reasons() -> None:
    profile = ProfileFactory.create(monthly_household_income=Decimal("20000"))
    assert hint_for(profile, None) == "Add your current school to see it."
    assert (
        hint_for(profile, academic(gwa_scale=School.Scale.ONE_TO_FIVE))
        == "The legacy model only reads percent grades."
    )
    assert hint_for(profile, academic(gwa=None)) == "The legacy model only reads percent grades."
    no_income = ProfileFactory.create(monthly_household_income=None)
    assert hint_for(no_income, academic()) == "Add your household income to see it."
    assert (
        hint_for(profile, academic(school_name="")) == "Add your school's name and type to see it."
    )
    assert (
        hint_for(profile, academic(school_type="")) == "Add your school's name and type to see it."
    )
    assert isinstance(hint_for(profile, academic()), Hint)


@pytest.mark.django_db
def test_hint_maps_suc_and_lcu_to_public() -> None:
    profile = ProfileFactory.create(monthly_household_income=Decimal("20000"))
    expected = hint_for(profile, academic(school_type="public"))
    assert isinstance(expected, Hint)
    for kind in ("suc", "lcu"):
        assert hint_for(profile, academic(school_type=kind)) == expected
