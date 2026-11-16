from typing import Any

from django.urls import reverse

from apps.matching.eligibility import EligibilityResult

CHECK_ICONS = {"met": "circle-check", "unmet": "circle-alert", "missing": "circle-help"}

# One label per check code `evaluate` can produce. Staff see these on the review screen, where the
# student-facing rule sentences ("You ...") would read wrongly.
CHECK_LABELS: dict[str, str] = {
    "window": "Applications were open",
    "school": "Has a current school",
    "allowed_schools": "Attends a listed school",
    "school_type": "Attends an allowed type of school",
    "units": "Carries enough units",
    "gwa": "Meets the grade requirement",
    "residency": "Meets the residency requirement",
    "voter": "Is a registered voter",
    "renewal_gwa": "Meets the renewal grade requirement",
    "renewal_units": "Carries enough units to renew",
    "no_failing": "Declared no failing, incomplete or dropped subjects",
}


def checklist_items(result: EligibilityResult) -> list[dict[str, str]]:
    """Items for components/checklist.html, one per eligibility check."""
    return [
        {
            "code": check.code,
            "state": check.state.value,
            "icon": CHECK_ICONS[check.state.value],
            "text": check.text,
            "detail": check.reason,
            "url": reverse(check.fix_url_name) if check.fix_url_name else "",
            "url_label": "Fix this in your profile",
        }
        for check in result.checks
    ]


def snapshot_items(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Items for components/checklist.html from a frozen `match_snapshot`."""
    checks = snapshot.get("checks") if isinstance(snapshot, dict) else None
    if not isinstance(checks, list):
        return []
    items = []
    for check in checks:
        if not isinstance(check, dict) or check.get("state") not in CHECK_ICONS:
            continue
        state = check["state"]
        code = str(check.get("code", ""))
        items.append(
            {
                "code": code,
                "state": state,
                "icon": CHECK_ICONS[state],
                "text": CHECK_LABELS.get(code, code.replace("_", " ").capitalize()),
                "detail": str(check.get("reason", "")) if state != "met" else "",
                "url": "",
                "url_label": "",
            }
        )
    return items
