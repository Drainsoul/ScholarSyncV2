"""The upload field: a file input that upload.ts turns into a direct-to-storage upload."""

from typing import Any

from django import template
from django.template import TemplateSyntaxError
from django.urls import reverse

from apps.files import policy

register = template.Library()


@register.filter
def types_label(types: list[str]) -> str:
    """MIME types in words: ["application/pdf", "image/png"] is "PDF or PNG"."""
    return policy.join_types(types) if types else ""


@register.inclusion_tag("components/file_input.html")
def upload_field(
    purpose: str,
    id: str,
    name: str,
    label: str,
    help: str = "",
    error: str = "",
    required: bool = False,
) -> dict[str, Any]:
    rule = policy.RULES.get(purpose)
    if rule is None:
        raise TemplateSyntaxError(f"upload_field: unknown purpose {purpose!r}")
    return {
        "id": id,
        "name": name,
        "label": label,
        "required": required,
        "help": help or policy.help_text(purpose),
        "state": "error" if error else "idle",
        "error": error,
        "upload": {
            "purpose": purpose,
            # text/plain is accepted only as a .csv name: offer the extension, not every text file.
            "accept": ",".join(".csv" if mime == policy.CSV_TEXT else mime for mime in rule.types),
            "max_bytes": rule.max_bytes,
            "intent_url": reverse("files:upload-intent"),
        },
    }
