"""File previews in the app dialog (spec §12 rev 27): pictures and PDFs, never served inline.

A picture's `<img>` loads through files:download, so its access check, the file.viewed audit and
the presigned attachment GET are the download's own. A PDF is drawn by pdf-preview.ts from a
presigned GET made here (audited the same way). Callers check access before calling."""

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers, patch_vary_headers

from apps.accounts.models import User

from . import services, storage
from .models import StoredFile
from .policy import JPEG, PDF, PNG

PREVIEW_TYPES = (PNG, JPEG, PDF)


def can_preview(file: StoredFile) -> bool:
    return file.sniffed_type in PREVIEW_TYPES


def render_preview(
    request: HttpRequest,
    *,
    user: User,
    file: StoredFile,
    label: str,
    back_url: str,
    layout: str,
    shell: dict[str, Any],
) -> HttpResponse:
    """The preview as a dialog fragment over HTMX, or as a page of its own in `layout`."""
    is_pdf = file.sniffed_type == PDF
    pdf_url = ""
    if is_pdf:
        try:
            pdf_url = services.download_url(user=user, file=file, request=request)
        except (storage.StorageNotConfigured, storage.StorageUnavailable):
            pdf_url = ""  # the dialog says the preview can't load; Download still shows
    dialog = bool(getattr(request, "htmx", False))
    response = render(
        request,
        "components/file_preview_dialog.html" if dialog else "components/file_preview_page.html",
        {
            **shell,
            "layout": layout,
            "file": file,
            "preview_label": label,
            "back_url": back_url,
            "is_pdf": is_pdf,
            "pdf_url": pdf_url,
        },
    )
    patch_vary_headers(response, ("HX-Request",))
    add_never_cache_headers(response)  # the PDF's presigned URL expires in 5 minutes
    return response
