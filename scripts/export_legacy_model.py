# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["scikit-learn==1.6.1", "numpy==1.26.4", "pandas==2.2.3", "joblib"]
# ///
"""Export the v1 scholarship tier model (scikit-learn) to JSON, with parity fixtures.

Run it once, by hand, with a pickle fetched read-only from the legacy repo (never commit the .pkl):

    mkdir -p "$SCRATCH/legacy-model" && gh api \
      "repos/Drainsoul/ScholarSync/contents/scholarship_tier_model.pkl?ref=fa9974c" \
      -H "Accept: application/vnd.github.raw" > "$SCRATCH/legacy-model/model.pkl"
    python -m uv run --script scripts/export_legacy_model.py "$SCRATCH/legacy-model/model.pkl" \
      apps/matching/data/legacy_tier_model.json apps/matching/tests/data/legacy_parity.json

Arguments: <path-to-pkl> <model-json-out> <parity-json-out>.

The pins match v1's requirements (numpy 1.26.4 has no Python 3.13 wheels, hence Python 3.12 here).
v1 loads the model with pickle.load; joblib.load reads the same file, with pickle as the fallback.
The script asserts the pipeline is standardise + one-hot + LogisticRegression and exits otherwise.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SOURCE = "Drainsoul/ScholarSync@fa9974c scholarship_tier_model.pkl"
NUMERIC = ["grade", "income"]
CATEGORICAL = ["school_name", "school_type"]
TOLERANCE = 1e-12

GRADES = [1.0, 1.01, 1.5, 2.0, 2.5, 3.0, 3.5, 3.99, 4.0]
INCOMES = [0, 5000, 18000, 50000, 250000]
SCHOOLS = [
    "Taguig City University",
    "University of Santo Tomas",
    "University of the Philippines",
    "Pateros Technological College",
    "taguig city university",
    "",
]
TYPES = ["public", "private", "other"]


def fail(message: str) -> None:
    sys.exit(f"export_legacy_model: {message}")


def load_model(path: Path) -> Any:
    try:
        import joblib

        return joblib.load(path)
    except Exception:
        with path.open("rb") as handle:
            return pickle.load(handle)  # noqa: S301


def find_parts(model: Any) -> tuple[ColumnTransformer, LogisticRegression]:
    if not isinstance(model, Pipeline) or len(model.steps) != 2:
        fail(
            f"expected a two-step Pipeline, found {type(model).__name__}"
            f": {getattr(model, 'steps', None)}"
        )
    pre, clf = model.steps[0][1], model.steps[1][1]
    if not isinstance(pre, ColumnTransformer):
        fail(f"first step is {type(pre).__name__}, expected ColumnTransformer")
    if not isinstance(clf, LogisticRegression):
        fail(f"last step is {type(clf).__name__}, expected LogisticRegression")
    return pre, clf


def check_transformers(pre: ColumnTransformer) -> tuple[StandardScaler, OneHotEncoder]:
    named = [
        (name, trans, list(cols)) for name, trans, cols in pre.transformers_ if name != "remainder"
    ]
    # v1 uses remainder="passthrough", harmless only because both transformers consume all
    # four input columns; the check on remainder columns below proves nothing is passed through.
    if any(name == "remainder" and list(cols) for name, _, cols in pre.transformers_):
        fail("the ColumnTransformer passes extra columns through, which the export does not model")
    print("transformers:", [(n, type(t).__name__, c) for n, t, c in named])
    if len(named) != 2:
        fail("expected exactly two transformers")
    (_, first, first_cols), (_, second, second_cols) = named
    if not (isinstance(first, StandardScaler) and first_cols == NUMERIC):
        fail("first transformer must be StandardScaler on grade, income")
    if not (isinstance(second, OneHotEncoder) and second_cols == CATEGORICAL):
        fail("second transformer must be OneHotEncoder on school_name, school_type")
    if not (first.with_mean and first.with_std):
        fail("StandardScaler must centre and scale")
    if second.handle_unknown != "ignore":
        fail(f"OneHotEncoder handle_unknown is {second.handle_unknown!r}, expected 'ignore'")
    if (
        second.drop is not None
        or second.max_categories is not None
        or second.min_frequency is not None
    ):
        fail(
            "OneHotEncoder uses drop/max_categories/min_frequency, which the export does not model"
        )
    return first, second


def fixture_rows() -> list[dict[str, Any]]:
    """A deterministic cross-section that covers every value at least once."""
    rows = [
        {
            "grade": GRADES[i % len(GRADES)],
            "income": INCOMES[(i * 2 + i // 5) % len(INCOMES)],
            "school_name": SCHOOLS[(i + i // 6) % len(SCHOOLS)],
            "school_type": TYPES[(i + i // 3) % len(TYPES)],
        }
        for i in range(36)
    ]
    for key, values in (
        ("grade", GRADES),
        ("income", INCOMES),
        ("school_name", SCHOOLS),
        ("school_type", TYPES),
    ):
        missing = set(values) - {row[key] for row in rows}
        if missing:
            fail(f"fixture cross-section misses {key} values {missing}")
    return rows


def softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def ovr(z: np.ndarray) -> np.ndarray:
    s = 1.0 / (1.0 + np.exp(-z))
    return s / s.sum(axis=1, keepdims=True)


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    pkl, model_out, parity_out = (Path(a) for a in sys.argv[1:])
    model = load_model(pkl)
    pre, clf = find_parts(model)
    scaler, encoder = check_transformers(pre)

    classes = [str(c) for c in clf.classes_]
    feature_order = [str(n) for n in pre.get_feature_names_out()]
    categories = [[str(v) for v in cats] for cats in encoder.categories_]
    expected = [f"num__{c}" for c in NUMERIC] + [
        f"cat__{col}_{v}" for col, cats in zip(CATEGORICAL, categories, strict=True) for v in cats
    ]
    if feature_order != expected:
        fail(f"feature order {feature_order} differs from numeric-then-categories {expected}")
    coef = clf.coef_
    if coef.shape != (len(classes), len(feature_order)):
        fail(
            f"coef shape {coef.shape} does not fit {len(classes)} classes"
            f" x {len(feature_order)} features"
        )
    print("classes:", classes)
    print("feature order:", feature_order)
    keys = ("penalty", "C", "solver", "multi_class", "fit_intercept", "class_weight")
    print("LogisticRegression:", {k: clf.get_params()[k] for k in keys})

    rows = fixture_rows()
    frame = pd.DataFrame({k: [r[k] for r in rows] for k in (*NUMERIC, *CATEGORICAL)})
    truth = np.asarray(model.predict_proba(frame), dtype=float)
    # Design matrix built by hand from the exported pieces (what the pure-Python port will do).
    x = np.zeros((len(rows), len(feature_order)))
    for i, col in enumerate(NUMERIC):
        x[:, i] = (frame[col].to_numpy(float) - scaler.mean_[i]) / scaler.scale_[i]
    index = len(NUMERIC)
    for col, cats in zip(CATEGORICAL, categories, strict=True):
        for j, value in enumerate(cats):
            x[:, index + j] = (frame[col] == value).to_numpy(float)
        index += len(cats)
    z = x @ coef.T + clf.intercept_
    errors = {
        "softmax": float(np.abs(softmax(z) - truth).max()),
        "ovr": float(np.abs(ovr(z) - truth).max()),
    }
    print("max abs error vs predict_proba:", errors)
    modes = [m for m, e in errors.items() if e <= TOLERANCE]
    if not modes:
        fail(f"neither softmax nor ovr matches predict_proba within {TOLERANCE}: {errors}")
    mode = modes[0]
    print("proba mode:", mode)

    payload = {
        "source": SOURCE,
        "sklearn": "1.6.1",
        "numeric": NUMERIC,
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "categorical": CATEGORICAL,
        "categories": categories,
        "feature_order": feature_order,
        "classes": classes,
        "coef": [[float(v) for v in row] for row in coef],
        "intercept": [float(v) for v in clf.intercept_],
        "proba": mode,
    }
    parity = [
        {**row, "proba": [float(p) for p in probs]} for row, probs in zip(rows, truth, strict=True)
    ]
    for path, data in ((model_out, payload), (parity_out, parity)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"parity rows: {len(parity)}")


if __name__ == "__main__":
    main()
