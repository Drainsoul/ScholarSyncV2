from apps.applications.staff_wording import NOT_ENTERED, staff_items


def item(code: str, state: str, detail: str) -> dict[str, str]:
    return {"code": code, "state": state, "text": "Rule", "detail": detail}


def test_staff_wording_renewal_missing_reads_not_entered() -> None:
    for code in ("renewal_gwa", "renewal_units"):
        [reworded] = staff_items([item(code, "missing", "Add your GWA.")], form=False)
        assert reworded["detail"] == NOT_ENTERED


def test_staff_wording_renewal_unmet_names_the_student() -> None:
    [reworded] = staff_items(
        [item("renewal_units", "unmet", "You have 12 units; renewing needs at least 15.")],
        form=False,
    )
    assert reworded["detail"] == "The student has 12 units; renewing needs at least 15."
