from decimal import Decimal

from apps.matching.checklist import CHECK_LABELS, snapshot_items
from apps.matching.eligibility import evaluate_renewal
from apps.matching.tests.test_eligibility import (
    TERM,
    TODAY,
    make_academic,
    make_profile,
    make_program,
    renewal_program,
    run,
)
from apps.programs.models import School


def test_snapshot_items_cover_every_check_code() -> None:
    program = make_program(allowed_school_types=["suc"])
    school = School(name="Other", type="private")
    result = run(
        program,
        make_profile(barangay="", residing_since=2025, is_registered_voter=False),
        make_academic(school=None, school_type="private", gwa=Decimal("60"), units=3),
        allowed_schools=(school,),
    )
    codes = {check.code for check in result.checks}
    assert codes == {
        "window",
        "school",
        "allowed_schools",
        "school_type",
        "units",
        "gwa",
        "residency",
        "voter",
    }
    assert codes <= set(CHECK_LABELS)
    renewal = evaluate_renewal(
        renewal_program(renewal_no_failing_grades=True),
        make_academic(),
        today=TODAY,
        term=TERM,
        declares_no_failing=None,
    )
    renewal_codes = {check.code for check in renewal.checks}
    assert set(CHECK_LABELS) == codes | renewal_codes


def test_snapshot_items_shows_reasons_only_when_not_met() -> None:
    items = snapshot_items(
        {
            "checks": [
                {"code": "gwa", "state": "unmet", "reason": "Too low."},
                {"code": "voter", "state": "missing", "reason": "Not given."},
                {"code": "units", "state": "met", "reason": ""},
            ]
        }
    )
    assert [i["detail"] for i in items] == ["Too low.", "Not given.", ""]
    assert items[0]["text"] == CHECK_LABELS["gwa"]
    assert items[0]["state"] == "unmet"


def test_snapshot_items_empty_or_unknown() -> None:
    assert snapshot_items({}) == []
    assert snapshot_items({"checks": "x"}) == []
    assert snapshot_items({"checks": [{"code": "gwa", "state": "weird"}]}) == []
    odd = snapshot_items({"checks": [{"code": "new_rule", "state": "met"}]})
    assert odd[0]["text"] == "New rule"


def test_snapshot_items_label_renewal_codes() -> None:
    snapshot = {
        "checks": [
            {"code": "renewal_gwa", "state": "met", "reason": ""},
            {"code": "renewal_units", "state": "unmet", "reason": "Too few."},
            {"code": "no_failing", "state": "missing", "reason": "Confirm."},
        ]
    }
    assert [item["text"] for item in snapshot_items(snapshot)] == [
        "Meets the renewal grade requirement",
        "Carries enough units to renew",
        "Declared no failing, incomplete or dropped subjects",
    ]


def test_snapshot_items_unknown_code_falls_back() -> None:
    items = snapshot_items({"checks": [{"code": "made_up", "state": "met", "reason": ""}]})
    assert items[0]["text"] == "Made up"
