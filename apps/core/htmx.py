"""HTMX response helpers (spec §12): toasts and dialog closing travel in HX-Trigger."""

from typing import Literal

from django.http import HttpRequest, HttpResponse
from django_htmx.http import trigger_client_event
from django_htmx.middleware import HtmxDetails

Tone = Literal["info", "success", "warning", "danger"]


class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails


def toast[R: HttpResponse](response: R, message: str, tone: Tone = "success") -> R:
    """toast.ts shows the message as text (never HTML) in the #toasts live region."""
    return trigger_client_event(response, "toast", {"message": message, "tone": tone})


def close_dialog[R: HttpResponse](response: R) -> R:
    """dialog.ts closes any open dialog."""
    return trigger_client_event(response, "closeDialog", {})
