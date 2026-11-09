from django.urls import reverse

from apps.matching.eligibility import EligibilityResult

CHECK_ICONS = {"met": "circle-check", "unmet": "circle-alert", "missing": "circle-help"}


def checklist_items(result: EligibilityResult) -> list[dict[str, str]]:
    """Items for components/checklist.html, one per eligibility check."""
    return [
        {
            "state": check.state.value,
            "icon": CHECK_ICONS[check.state.value],
            "text": check.text,
            "detail": check.reason,
            "url": reverse(check.fix_url_name) if check.fix_url_name else "",
            "url_label": "Fix this in your profile",
        }
        for check in result.checks
    ]
