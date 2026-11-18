"""Request ids for log lines (spec §10, M13; ASVS V16.2.1).

The first middleware keeps a valid incoming `X-Request-ID` (a proxy's) or makes one, returns it,
and remembers the request so `JsonFormatter` can add the request id and, once Django has loaded
it, the user id. Logging never loads the user itself: no queries while logging."""

import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.core.signals import request_finished
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse

VALID_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
CURRENT: ContextVar[tuple[str, HttpRequest] | None] = ContextVar("request_context", default=None)


def current_ids() -> dict[str, object]:
    """The request id and, if Django already loaded the user, the user id."""
    context = CURRENT.get()
    if context is None:
        return {}
    request_id, request = context
    ids: dict[str, object] = {"request_id": request_id}
    user = getattr(request, "_cached_user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        ids["user_id"] = user.pk
    return ids


class RequestContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if VALID_ID.fullmatch(incoming) else uuid.uuid4().hex
        # Kept until the response is finished: Django logs "Not Found" and server errors after
        # the middleware chain returns.
        CURRENT.set((request_id, request))
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


@receiver(request_finished)
def _clear(sender: object, **kwargs: object) -> None:
    CURRENT.set(None)
