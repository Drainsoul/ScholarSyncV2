"""Pure-Python port of v1's tier model, shown as an advisory hint only.

The coefficients come from ``data/legacy_tier_model.json`` (exported by
``scripts/export_legacy_model.py``). Nothing here decides eligibility.
"""

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from apps.matching.eligibility import Academic
from apps.programs.models import School
from apps.students.models import StudentProfile

MODEL_PATH = Path(__file__).parent / "data" / "legacy_tier_model.json"


@dataclass(frozen=True)
class Hint:
    label: str
    program_slug: str | None
    merit: bool
    probability: float


def _validate(model: dict[str, Any]) -> dict[str, Any]:
    if model["proba"] not in ("softmax", "ovr"):
        raise ValueError(f"Unknown probability mode: {model['proba']!r}")
    names = [f"num__{c}" for c in model["numeric"]]
    for column, categories in zip(model["categorical"], model["categories"], strict=True):
        names += [f"cat__{column}_{c}" for c in categories]
    assert names == model["feature_order"], "feature order mismatch"
    return model


@cache
def _load() -> dict[str, Any]:
    with MODEL_PATH.open(encoding="utf-8") as handle:
        return _validate(json.load(handle))


def grade_from_percent(gwa: Decimal) -> float:
    return round(min(4.0, max(1.0, 1.0 + (float(gwa) - 70.0) * (3.0 / 30.0))), 2)


def predict_proba(
    *, grade: float, income: float, school_name: str, school_type: str
) -> list[float]:
    model = _load()
    raw = {"grade": grade, "income": income}
    features = [
        (float(raw[column]) - mean) / scale
        for column, mean, scale in zip(model["numeric"], model["mean"], model["scale"], strict=True)
    ]
    values = {"school_name": school_name, "school_type": school_type}
    for column, categories in zip(model["categorical"], model["categories"], strict=True):
        features += [1.0 if values[column] == c else 0.0 for c in categories]
    scores = [
        sum(w * x for w, x in zip(row, features, strict=True)) + b
        for row, b in zip(model["coef"], model["intercept"], strict=True)
    ]
    if model["proba"] == "softmax":
        top = max(scores)
        exps = [math.exp(s - top) for s in scores]
        total = sum(exps)
        return [e / total for e in exps]
    sigmoids = [1.0 / (1.0 + math.exp(-s)) for s in scores]
    total = sum(sigmoids)
    return [s / total for s in sigmoids]


def _program_for(label: str) -> str | None:
    if label.startswith("CEAA_"):
        return "tcu-ceaa"
    if label.startswith("LANI_"):
        return "lani"
    return None


def suggest(*, gwa_percent: Decimal, income: Decimal, school_name: str, school_type: str) -> Hint:
    if school_type in (School.Type.SUC, School.Type.LCU):
        school_type = School.Type.PUBLIC
    probabilities = predict_proba(
        grade=grade_from_percent(gwa_percent),
        income=float(income),
        school_name=school_name,
        school_type=str(school_type),
    )
    best = max(range(len(probabilities)), key=probabilities.__getitem__)
    label: str = _load()["classes"][best]
    return Hint(
        label=label,
        program_slug=_program_for(label),
        merit=label.endswith("_Merit"),
        probability=probabilities[best],
    )


def hint_for(profile: StudentProfile, academic: Academic | None) -> Hint | str:
    if academic is None:
        return "Add your current school to see it."
    if academic.gwa_scale != School.Scale.PERCENT or academic.gwa is None:
        return "The legacy model only reads percent grades."
    if profile.monthly_household_income is None:
        return "Add your household income to see it."
    if not academic.school_name or not academic.school_type:
        return "Add your school's name and type to see it."
    return suggest(
        gwa_percent=academic.gwa,
        income=profile.monthly_household_income,
        school_name=academic.school_name,
        school_type=academic.school_type,
    )
