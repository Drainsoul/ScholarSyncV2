from django import template

register = template.Library()

TONES = {"submitted": "warning", "accepted": "success", "returned": "danger"}


@register.filter
def report_tone(status: str) -> str:
    """The status tone of a report: waiting warning, accepted success, returned danger."""
    return TONES.get(status, "neutral")
