"""Staff-facing wording for eligibility checks.

The shared engine writes its reasons for students ("Add your GWA to your profile."). Staff see the
same checks while filing or reviewing, where those sentences point at the wrong person and the
wrong place, so the staff views swap them here. The student copy is not touched.
"""

from apps.matching.checklist import CHECK_LABELS

ACADEMIC_CODES = frozenset({"school", "allowed_schools", "school_type", "units", "gwa"})
PROFILE_CODES = frozenset({"residency", "voter"})

ENTER_ABOVE = "Enter this in School and grades above."
NOT_ENTERED = "Not entered when the application was filed."
NOT_ON_PROFILE = "Not on the student's profile. Override with a reason, or ask the student."


def staff_items(items: list[dict[str, str]], *, form: bool) -> list[dict[str, str]]:
    """Items with `detail` reworded for staff; `form` says the page has the grades form."""
    return [{**item, "text": _text(item), "detail": _detail(item, form=form)} for item in items]


def _text(item: dict[str, str]) -> str:
    """The rule sentence, except the one written as "You have a current school in your profile"."""
    if item.get("code") == "school":
        return CHECK_LABELS["school"]
    return item["text"]


def _detail(item: dict[str, str], *, form: bool) -> str:
    detail = item["detail"]
    code, state = item.get("code", ""), item["state"]
    if state == "missing" and code in ACADEMIC_CODES:
        return ENTER_ABOVE if form else NOT_ENTERED
    if state == "missing" and code in PROFILE_CODES:
        return NOT_ON_PROFILE
    if detail.startswith("Your "):
        return "The student's " + detail.removeprefix("Your ")
    if detail.startswith("You have "):
        return "The student has " + detail.removeprefix("You have ")
    return detail
