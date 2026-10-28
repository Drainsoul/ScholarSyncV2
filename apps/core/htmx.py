"""HTMX response helpers (spec §12): toasts and dialog closing travel in HX-Trigger.

Protocol for a form in the app dialog (hx-target="#app-dialog-body"), which later screens copy:
- validation error: re-render the dialog fragment, with the errors, as a 200 into #app-dialog-body;
- success: 204 + close_dialog(toast(response, "…")), which closes the dialog and shows the toast;
- failure (4xx/5xx, or no connection): nothing special; toast.ts shows the global danger toast
  ("Something went wrong on our side…" or "We couldn't reach the server…"); the dialog stays open.
A full-page (no-JS) request gets the same form as a page, then a redirect with a Django message.
"""

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
