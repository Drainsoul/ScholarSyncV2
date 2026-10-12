from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class PermissionsPolicyMiddleware:
    """Adds the Permissions-Policy header (Django has no setting for it)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        return response
