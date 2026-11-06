"""Upload and download services: presign, verify and audit stored files.

The browser PUTs straight to ``pending/<id>`` with a presigned URL that stays valid for ten
minutes, so the pending object can change while it is being checked. Confirm therefore copies
it to ``files/<purpose>/<id>`` first and checks only the copy (photos: one read, checked and
re-encoded from those bytes).
"""

import hashlib
import io
import math
import uuid
import warnings
from dataclasses import dataclass
from datetime import timedelta

import filetype
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from PIL import Image, ImageOps

from apps.accounts.models import User
from apps.core.audit import record

from . import policy, storage
from .models import StoredFile, pending_key
from .names import clean_filename, content_disposition, download_name

REJECTIONS: dict[str, str] = {
    "missing": "We didn't receive your file. Try uploading it again.",
    "size": "The file we received isn't the size we expected. Try uploading it again.",
    "type": "This isn't a valid {types_phrase} file.",
    "image": "We couldn't read this image. Upload a different JPG or PNG.",
}

_IMAGE_ERRORS = (
    OSError,  # includes PIL.UnidentifiedImageError
    ValueError,
    SyntaxError,
    EOFError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
)
_FORMATS = {policy.JPEG: "JPEG", policy.PNG: "PNG"}


class UploadRejected(Exception):
    """An upload the rules refuse; `message` is shown to the user, `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class _Rejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UploadIntent:
    file: StoredFile
    url: str
    headers: dict[str, str]


def rejection_message(file: StoredFile) -> str:
    template = REJECTIONS.get(file.rejected_reason, REJECTIONS["missing"])
    phrase = (
        policy.types_phrase(file.purpose) if file.purpose in policy.RULES else "PDF, JPG or PNG"
    )
    return template.format(types_phrase=phrase)


def _check_start(*, user: User, purpose: str, content_type: str, size: int) -> None:
    rule = policy.RULES.get(purpose)
    if rule is None:
        raise UploadRejected("This upload isn't available.", 400)
    if user.role not in rule.roles:
        raise UploadRejected("You can't upload this kind of file.", 403)
    if content_type not in rule.types:
        raise UploadRejected(f"You can upload a {policy.types_phrase(purpose)} file here.", 400)
    if size <= 0:
        raise UploadRejected("This file is empty. Choose another file.", 400)
    if size > rule.max_bytes:
        size_mb = math.ceil(size / policy.MB)
        max_mb = rule.max_bytes // policy.MB
        raise UploadRejected(
            f"This file is {size_mb} MB. Upload a file of {max_mb} MB or less.", 400
        )
    since = timezone.now() - timedelta(hours=1)
    recent = StoredFile.objects.filter(uploaded_by=user, created_at__gt=since).count()
    if recent >= policy.STARTS_PER_HOUR:
        raise UploadRejected(
            "You've started too many uploads in the last hour. Try again later.", 429
        )


@transaction.atomic
def start_upload(
    *,
    user: User,
    purpose: str,
    name: str,
    content_type: str,
    size: int,
    request: HttpRequest | None = None,
) -> UploadIntent:
    """Validate the request, create the pending row and return a presigned PUT for it."""
    _check_start(user=user, purpose=purpose, content_type=content_type, size=size)
    if not storage.is_configured():
        raise storage.StorageNotConfigured("Object storage is not configured.")
    file_id = uuid.uuid4()
    file = StoredFile.objects.create(
        id=file_id,
        key=pending_key(file_id),
        status=StoredFile.Status.PENDING,
        purpose=purpose,
        original_name=clean_filename(name),
        declared_type=content_type,
        size=size,
        uploaded_by=user,
    )
    record(
        actor=user,
        action="file.upload_started",
        target=file,
        data={"purpose": purpose, "size": size, "type": content_type},
        request=request,
    )
    url = storage.presigned_put(key=file.key, content_type=content_type, size=size)
    return UploadIntent(file=file, url=url, headers={"Content-Type": content_type})


def _sniff(head: bytes) -> str:
    return filetype.guess_mime(head) or ""


def _verify_object(file: StoredFile) -> tuple[str, int, str]:
    """Documents and reports: copy, then check only the copy. Returns (type, size, sha256)."""
    final = file.final_key
    copied = storage.copy(source=file.key, dest=final, content_type=file.declared_type)
    if not copied and storage.head_size(final) is None:
        # Nothing at either key. (A final object with no pending one means an earlier confirm
        # copied it and then lost storage; that copy is server-made, so it is checked below.)
        raise _Rejected("missing")
    try:
        storage.delete(file.key)
        if storage.head_size(final) != file.size:
            raise _Rejected("size")
        sniffed = _sniff(storage.read_range(final, policy.SNIFF_BYTES))
        if sniffed != file.declared_type:
            raise _Rejected("type")
        digest = hashlib.sha256()
        for chunk in storage.iter_chunks(final):
            digest.update(chunk)
    except _Rejected:
        storage.delete(final)
        raise
    return sniffed, file.size, digest.hexdigest()


def _reencode(body: bytes, mime: str) -> bytes:
    """Open, bound, orient and re-encode an image, dropping EXIF and ICC data."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            opened = Image.open(io.BytesIO(body))
            width, height = opened.size
            if width * height > policy.MAX_IMAGE_PIXELS:
                raise _Rejected("image")
            if opened.format != _FORMATS[mime]:
                raise _Rejected("image")
            opened.load()
            image = ImageOps.exif_transpose(opened)
            image.info.clear()
            out = io.BytesIO()
            if mime == policy.JPEG:
                if image.mode not in ("RGB", "L", "CMYK"):
                    image = image.convert("RGB")
                image.save(out, format="JPEG", quality=90, exif=b"", icc_profile=None)
            else:
                image.save(out, format="PNG", optimize=True, exif=b"", icc_profile=None)
    except _IMAGE_ERRORS as exc:
        raise _Rejected("image") from exc
    return out.getvalue()


def _verify_photo(file: StoredFile) -> tuple[str, int, str]:
    """Photos: one read of the pending object; everything is checked and re-encoded from it."""
    if storage.head_size(file.key) is None:
        raise _Rejected("missing")
    body = storage.read_all(file.key)
    try:
        if len(body) != file.size:
            raise _Rejected("size")
        sniffed = _sniff(body[: policy.SNIFF_BYTES])
        if sniffed != file.declared_type:
            raise _Rejected("type")
        clean = _reencode(body, sniffed)
    except _Rejected:
        storage.delete(file.key)
        raise
    storage.put(key=file.final_key, body=clean, content_type=sniffed)
    storage.delete(file.key)
    return sniffed, len(clean), hashlib.sha256(clean).hexdigest()


@transaction.atomic
def confirm_upload(
    *, user: User, file_id: uuid.UUID, request: HttpRequest | None = None
) -> StoredFile:
    """Verify the user's pending upload and mark it ready or rejected.

    A bad file never raises: the rejection is saved and returned. Storage errors propagate and
    roll back, leaving the row pending so it can be confirmed again once storage is back.
    """
    file = StoredFile.objects.select_for_update().get(pk=file_id, uploaded_by=user)
    if file.status != StoredFile.Status.PENDING:
        return file
    verify = _verify_photo if file.purpose == StoredFile.Purpose.PHOTO else _verify_object
    try:
        sniffed, size, sha256 = verify(file)
    except _Rejected as rejected:
        file.status = StoredFile.Status.REJECTED
        file.rejected_reason = rejected.reason
        file.save(update_fields=["status", "rejected_reason", "updated_at"])
        record(
            actor=user,
            action="file.rejected",
            target=file,
            data={"reason": rejected.reason},
            request=request,
        )
        return file
    file.status = StoredFile.Status.READY
    file.key = file.final_key
    file.sniffed_type = sniffed
    file.size = size
    file.sha256 = sha256
    file.save(update_fields=["status", "key", "sniffed_type", "size", "sha256", "updated_at"])
    record(
        actor=user,
        action="file.uploaded",
        target=file,
        data={"purpose": file.purpose, "size": size, "type": sniffed},
        request=request,
    )
    return file


@transaction.atomic
def download_url(*, user: User, file: StoredFile, request: HttpRequest | None = None) -> str:
    """Audit the view and return a short-lived presigned GET sent as an attachment."""
    record(actor=user, action="file.viewed", target=file, program=None, request=request)
    return storage.presigned_get(
        key=file.final_key,
        content_type=file.sniffed_type,
        disposition=content_disposition(download_name(file.original_name, file.sniffed_type)),
    )
