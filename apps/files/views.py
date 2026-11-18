"""JSON and redirect endpoints for the browser uploader. Views stay thin: services do the work."""

import json
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_GET, require_POST

from . import scanning, selectors, services, storage
from .models import StoredFile

UNREADABLE = "We couldn't read that upload request."
NOT_CONFIGURED = "File uploads aren't set up on this copy of ScholarSync."
UNAVAILABLE = "File storage isn't available right now. Try again in a few minutes."
SCANNER_UNAVAILABLE = "Files can't be checked right now. Try again in a few minutes."
TEXT = "text/plain; charset=utf-8"


def _error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _json_api(view: Callable[..., JsonResponse]) -> Callable[..., JsonResponse]:
    """Signed-in users only (401 JSON otherwise); storage errors become a 503 sentence."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        if not request.user.is_authenticated:
            return _error("Sign in to upload files.", 401)
        try:
            return view(request, *args, **kwargs)
        except storage.StorageNotConfigured:
            return _error(NOT_CONFIGURED, 503)
        except storage.StorageUnavailable:
            return _error(UNAVAILABLE, 503)
        except scanning.ScannerUnavailable:
            return _error(SCANNER_UNAVAILABLE, 503)

    return wrapper


def _parse_intent(request: HttpRequest) -> tuple[str, str, str, int] | None:
    try:
        body = json.loads(request.body)
    except (ValueError, RecursionError):
        # RecursionError: a deeply nested body overflows the JSON parser's stack.
        return None
    if not isinstance(body, dict):
        return None
    purpose, name, content_type, size = (body.get(k) for k in ("purpose", "name", "type", "size"))
    if not (
        isinstance(purpose, str)
        and isinstance(name, str)
        and isinstance(content_type, str)
        and isinstance(size, int)
        and not isinstance(size, bool)
    ):
        return None
    return purpose, name, content_type, size


@require_POST
@_json_api
def upload_intent(request: HttpRequest) -> JsonResponse:
    parsed = _parse_intent(request)
    if parsed is None:
        return _error(UNREADABLE, 400)
    purpose, name, content_type, size = parsed
    try:
        intent = services.start_upload(
            user=request.user,  # type: ignore[arg-type]
            purpose=purpose,
            name=name,
            content_type=content_type,
            size=size,
            request=request,
        )
    except services.UploadRejected as rejected:
        return _error(rejected.message, rejected.status)
    file_id = intent.file.id
    return JsonResponse(
        {
            "id": str(file_id),
            "url": intent.url,
            "headers": intent.headers,
            "confirm_url": reverse("files:upload-confirm", kwargs={"file_id": file_id}),
        },
        status=201,
    )


@require_POST
@_json_api
def upload_confirm(request: HttpRequest, file_id: uuid.UUID) -> JsonResponse:
    try:
        file = services.confirm_upload(
            user=request.user,  # type: ignore[arg-type]
            file_id=file_id,
            request=request,
        )
    except StoredFile.DoesNotExist:
        return _error("Upload not found.", 404)
    if file.status != StoredFile.Status.READY:
        return _error(services.rejection_message(file), 400)
    return JsonResponse(
        {
            "id": str(file.id),
            "name": file.original_name,
            "size": file.size,
            "download_url": reverse("files:download", kwargs={"file_id": file.id}),
        }
    )


@require_GET
def download(request: HttpRequest, file_id: uuid.UUID) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    user = request.user
    file = selectors.downloadable_file(user, file_id)
    try:
        url = services.download_url(user=user, file=file, request=request)
    except storage.StorageNotConfigured:
        return HttpResponse(NOT_CONFIGURED, status=503, content_type=TEXT)
    except storage.StorageUnavailable:
        return HttpResponse(UNAVAILABLE, status=503, content_type=TEXT)
    response = redirect(url)
    add_never_cache_headers(response)
    return response
