"""The upload field: a file input that upload.ts turns into a direct-to-storage upload."""

from typing import Any

from django import template
from django.template import TemplateSyntaxError
from django.urls import reverse

from apps.files import policy

register = template.Library()


@register.inclusion_tag("components/file_input.html")
def upload_field(purpose: str, id: str, name: str, label: str, help: str = "") -> dict[str, Any]:
    rule = policy.RULES.get(purpose)
    if rule is None:
        raise TemplateSyntaxError(f"upload_field: unknown purpose {purpose!r}")
    return {
        "id": id,
        "name": name,
        "label": label,
        "help": help or policy.help_text(purpose),
        "state": "idle",
        "upload": {
            "purpose": purpose,
            "accept": ",".join(rule.types),
            "max_bytes": rule.max_bytes,
            "intent_url": reverse("files:upload-intent"),
        },
    }
