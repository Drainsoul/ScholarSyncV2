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


def test_staff_wording_for_residency_and_gwa_scale() -> None:
    residency, scale = staff_items(
        [
            item(
                "residency",
                "unmet",
                "This program needs at least 3 years in Taguig; your profile says since 2025.",
            ),
            item(
                "gwa",
                "unmet",
                "This program has no grade rule yet for schools that grade on a 1-5 scale. "
                "Ask the scholarship office.",
            ),
        ],
        form=False,
    )
    assert residency["detail"] == "Residency since 2025 is under the 3-year rule."
    assert scale["detail"] == "This program has no rule for 1-5 grades."
