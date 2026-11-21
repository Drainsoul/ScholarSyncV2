from django import template

register = template.Library()

TONES = {
    "with_head": "warning",
    "approved": "info",
    "submitted": "warning",
    "accepted": "success",
    "returned": "danger",
}


OFFICE_LABELS = {"submitted": "To review"}


@register.filter
def office_report_label(report: object) -> str:
    """The status as the office reads it: a submitted report is one to review."""
    status = getattr(report, "status", "")
    return OFFICE_LABELS.get(status) or report.get_status_display()  # type: ignore[attr-defined]


@register.filter
def report_tone(status: str) -> str:
    """The status tone of a report: waiting warning, approved info, accepted success, returned
    danger."""
    return TONES.get(status, "neutral")
