from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.cache import patch_cache_control

from apps.core.redaction import SECRET_PATHS


class PermissionsPolicyMiddleware:
    """Adds the Permissions-Policy header (Django has no setting for it)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        return response


class NoStoreMiddleware:
    """Browsers never keep a signed-in page or a secret-link page (spec §10, M12).

    A shared computer's back button or disk cache would otherwise show a student's pages to the
    next person. A view that set its own Cache-Control (exports, downloads) keeps it."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if response.has_header("Cache-Control"):
            return response
        user = getattr(request, "user", None)
        signed_in = user is not None and user.is_authenticated
        if signed_in or any(pattern.search(request.path) for pattern in SECRET_PATHS):
            patch_cache_control(response, no_store=True, private=True)
        return response
