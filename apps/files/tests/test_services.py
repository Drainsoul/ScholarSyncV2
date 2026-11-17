import datetime as dt
import hashlib
import io
import struct
import uuid
from zoneinfo import ZoneInfo

import pytest
import requests
import time_machine
from PIL import Image

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.files import policy, services, storage
from apps.files.models import StoredFile
from apps.files.services import UploadIntent, UploadRejected
from apps.files.storage import StorageNotConfigured, StorageUnavailable

from .conftest import jpeg_with_exif, pdf_bytes, png_bytes

pytestmark = pytest.mark.django_db

MB = 1024 * 1024


def upload(intent: UploadIntent, body: bytes) -> None:
    response = requests.put(intent.url, data=body, headers=intent.headers, timeout=10)
    response.raise_for_status()


def start(
    user: User, body: bytes, *, purpose: str = "document", content_type: str = "application/pdf"
):
    return services.start_upload(
        user=user, purpose=purpose, name="grades.pdf", content_type=content_type, size=len(body)
    )


def objects(s3) -> set[str]:
    response = s3.list_objects_v2(Bucket=s3.bucket)
    return {obj["Key"] for obj in response.get("Contents", [])}


def actions(file: StoredFile) -> list[str]:
    return list(
        AuditEvent.objects.filter(target_id=str(file.pk))
        .order_by("id")
        .values_list("action", flat=True)
    )


@pytest.fixture
def student():
    return UserFactory.create(verified=True)


def test_start_upload_creates_pending_row_and_audits(s3, student):
    intent = services.start_upload(
        user=student,
        purpose="document",
        name="../Peñafrancia – grades.PDF",
        content_type="application/pdf",
        size=1234,
    )
    file = StoredFile.objects.get()
    assert intent.file == file
    assert file.key == f"pending/{file.id}"
    assert file.status == StoredFile.Status.PENDING
    assert file.original_name == "Peñafrancia – grades.PDF"
    assert file.declared_type == "application/pdf"
    assert file.size == 1234
    assert file.uploaded_by == student
    assert intent.headers == {"Content-Type": "application/pdf"}
    assert f"pending/{file.id}" in intent.url
    event = AuditEvent.objects.get(action="file.upload_started")
    assert event.actor == student
    assert event.target_id == str(file.id)
    assert event.data == {"purpose": "document", "size": 1234, "type": "application/pdf"}
    assert "name" not in event.data


@pytest.mark.parametrize(
    ("purpose", "content_type", "size", "role", "status", "message"),
    [
        (
            "document",
            "image/svg+xml",
            100,
            User.Role.STUDENT,
            400,
            "You can upload a PDF, JPG or PNG file here.",
        ),
        (
            "photo",
            "text/html",
            100,
            User.Role.STUDENT,
            400,
            "You can upload a JPG or PNG file here.",
        ),
        (
            "document",
            "application/pdf",
            0,
            User.Role.STUDENT,
            400,
            "This file is empty. Choose another file.",
        ),
        (
            "document",
            "application/pdf",
            10 * MB + 1,
            User.Role.STUDENT,
            400,
            "This file is 11 MB. Upload a file of 10 MB or less.",
        ),
        (
            "export",
            "application/pdf",
            100,
            User.Role.SUPER_ADMIN,
            400,
            "This upload isn't available.",
        ),
        (
            "nonsense",
            "application/pdf",
            100,
            User.Role.STUDENT,
            400,
            "This upload isn't available.",
        ),
        (
            "report",
            "application/pdf",
            100,
            User.Role.STUDENT,
            403,
            "You can't upload this kind of file.",
        ),
    ],
)
def test_start_upload_rejects(s3, purpose, content_type, size, role, status, message):
    user = UserFactory.create(verified=True, role=role)
    with pytest.raises(UploadRejected) as excinfo:
        services.start_upload(
            user=user, purpose=purpose, name="x", content_type=content_type, size=size
        )
    assert excinfo.value.status == status
    assert excinfo.value.message == message
    assert StoredFile.objects.count() == 0
    assert not AuditEvent.objects.filter(action="file.upload_started").exists()


def test_staff_may_upload_a_report(s3):
    staff = UserFactory.create(verified=True, role=User.Role.STAFF)
    intent = services.start_upload(
        user=staff, purpose="report", name="r.pdf", content_type="application/pdf", size=20 * MB
    )
    assert intent.file.purpose == "report"


def test_twenty_starts_per_hour(s3, student):
    start_at = dt.datetime(2026, 11, 6, 9, 0, tzinfo=ZoneInfo("Asia/Manila"))
    with time_machine.travel(start_at, tick=False) as traveller:
        for _ in range(policy.STARTS_PER_HOUR):
            start(student, b"x" * 10)
        with pytest.raises(UploadRejected) as excinfo:
            start(student, b"x" * 10)
        assert excinfo.value.status == 429
        assert excinfo.value.message == (
            "You've started too many uploads in the last hour. Try again later."
        )
        assert StoredFile.objects.count() == policy.STARTS_PER_HOUR
        traveller.shift(dt.timedelta(hours=1))
        start(student, b"x" * 10)
    assert StoredFile.objects.count() == policy.STARTS_PER_HOUR + 1


def test_not_configured_writes_nothing(settings, student):
    settings.S3_STORAGE = {**settings.S3_STORAGE, "bucket": ""}
    with pytest.raises(StorageNotConfigured):
        start(student, pdf_bytes())
    assert StoredFile.objects.count() == 0
    assert AuditEvent.objects.count() == 0


def test_confirm_pdf_makes_it_ready(s3, student):
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == "application/pdf"
    assert file.sha256 == hashlib.sha256(body).hexdigest()
    assert file.size == len(body)
    assert objects(s3) == {file.final_key}
    assert storage.read_all(file.final_key) == body
    file.refresh_from_db()
    assert file.status == StoredFile.Status.READY
    assert actions(file) == ["file.upload_started", "file.uploaded"]
    event = AuditEvent.objects.get(action="file.uploaded")
    assert event.data == {"purpose": "document", "size": len(body), "type": "application/pdf"}


def test_confirm_rejects_fake_pdf(s3, student):
    body = b"just some text pretending to be a pdf"
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "type"
    assert services.rejection_message(file) == "This isn't a valid PDF, JPG or PNG file."
    assert objects(s3) == set()
    file.refresh_from_db()
    assert file.status == StoredFile.Status.REJECTED
    assert AuditEvent.objects.get(action="file.rejected").data == {"reason": "type"}


def test_confirm_rejects_missing_object(s3, student):
    intent = start(student, pdf_bytes())
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "missing"
    assert (
        services.rejection_message(file) == "We didn't receive your file. Try uploading it again."
    )


def test_confirm_rejects_wrong_size(s3, student):
    body = pdf_bytes()
    intent = services.start_upload(
        user=student,
        purpose="document",
        name="a.pdf",
        content_type="application/pdf",
        size=len(body) + 5,
    )
    s3.put_object(Bucket=s3.bucket, Key=intent.file.key, Body=body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.rejected_reason == "size"
    assert objects(s3) == set()


def test_photo_stored_with_a_different_size_is_rejected_before_reading(s3, student, monkeypatch):
    body = png_bytes()
    intent = start(student, body, purpose="photo", content_type="image/png")
    s3.put_object(Bucket=s3.bucket, Key=intent.file.key, Body=body + b"x" * 100)

    def no_read(key):
        raise AssertionError("read_all must not run")

    monkeypatch.setattr(storage, "read_all", no_read)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.rejected_reason == "size"
    assert objects(s3) == set()


def test_confirm_checks_the_copy_not_the_pending_object(s3, student, monkeypatch):
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    original_delete = storage.delete

    def overwrite_then_delete(key: str) -> None:
        if key == intent.file.key:
            s3.put_object(Bucket=s3.bucket, Key=key, Body=b"swapped for plain text")
        original_delete(key)

    monkeypatch.setattr(storage, "delete", overwrite_then_delete)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert file.sha256 == hashlib.sha256(body).hexdigest()
    assert storage.read_all(file.final_key) == body


def test_confirm_is_idempotent(s3, student):
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    first = services.confirm_upload(user=student, file_id=intent.file.id)
    second = services.confirm_upload(user=student, file_id=intent.file.id)
    assert second == first
    assert second.status == StoredFile.Status.READY
    assert second.sha256 == first.sha256
    assert AuditEvent.objects.filter(action="file.uploaded").count() == 1


def test_confirm_rejected_file_is_returned_unchanged(s3, student):
    intent = start(student, pdf_bytes())
    services.confirm_upload(user=student, file_id=intent.file.id)
    again = services.confirm_upload(user=student, file_id=intent.file.id)
    assert again.rejected_reason == "missing"
    assert AuditEvent.objects.filter(action="file.rejected").count() == 1


def test_confirm_other_users_file_does_not_exist(s3, student):
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    other = UserFactory.create(verified=True)
    with pytest.raises(StoredFile.DoesNotExist):
        services.confirm_upload(user=other, file_id=intent.file.id)
    with pytest.raises(StoredFile.DoesNotExist):
        services.confirm_upload(user=student, file_id=uuid.uuid4())
    intent.file.refresh_from_db()
    assert intent.file.status == StoredFile.Status.PENDING


def test_photo_exif_is_stripped_and_orientation_applied(s3, student):
    body = jpeg_with_exif(orientation=6)
    intent = start(student, body, purpose="photo", content_type="image/jpeg")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == "image/jpeg"
    stored = storage.read_all(file.final_key)
    assert file.size == len(stored)
    assert file.sha256 == hashlib.sha256(stored).hexdigest()
    image = Image.open(io.BytesIO(stored))
    assert image.size == (10, 20)
    assert dict(image.getexif()) == {}
    assert "icc_profile" not in image.info
    assert objects(s3) == {file.final_key}


def test_photo_png_is_reencoded(s3, student):
    body = png_bytes()
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == "image/png"
    assert Image.open(io.BytesIO(storage.read_all(file.final_key))).size == (20, 10)


def test_photo_over_the_pixel_cap_is_rejected(s3, student, monkeypatch):
    monkeypatch.setattr(policy, "MAX_IMAGE_PIXELS", 100)
    body = png_bytes(20, 10)
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "image"
    assert (
        services.rejection_message(file)
        == "We couldn't read this image. Upload a different JPG or PNG."
    )
    assert objects(s3) == set()


def test_photo_that_is_not_an_image_is_rejected(s3, student):
    body = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "image"
    assert objects(s3) == set()


def test_photo_declared_png_but_jpeg_is_rejected(s3, student):
    body = jpeg_with_exif()
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.rejected_reason == "type"
    assert services.rejection_message(file) == "This isn't a valid JPG or PNG file."
    assert objects(s3) == set()


def test_photo_missing_is_rejected(s3, student):
    intent = start(student, png_bytes(), purpose="photo", content_type="image/png")
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.rejected_reason == "missing"


def test_storage_down_leaves_the_file_pending(s3, student, monkeypatch):
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)

    def broken_copy(**kwargs: object) -> bool:
        raise StorageUnavailable("down")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "copy", broken_copy)
        with pytest.raises(StorageUnavailable):
            services.confirm_upload(user=student, file_id=intent.file.id)
    intent.file.refresh_from_db()
    assert intent.file.status == StoredFile.Status.PENDING
    assert not AuditEvent.objects.filter(action__in=["file.uploaded", "file.rejected"]).exists()
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY


def test_download_url_audits_and_uses_the_sniffed_type(s3, student):
    body = pdf_bytes()
    intent = services.start_upload(
        user=student,
        purpose="document",
        name="Peña grades",
        content_type="application/pdf",
        size=len(body),
    )
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    url = services.download_url(user=student, file=file)
    event = AuditEvent.objects.get(action="file.viewed")
    assert event.actor == student
    assert event.target_id == str(file.id)
    assert event.program is None
    assert event.data == {}
    response = requests.get(url, timeout=10)
    assert response.status_code == 200
    assert response.content == body
    assert response.headers["Content-Type"] == "application/pdf"
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith('attachment; filename="Pena grades.pdf"')
    assert "filename*=UTF-8''Pe%C3%B1a%20grades.pdf" in disposition


def test_policy_help_text():
    assert policy.help_text("document") == "PDF, JPG or PNG, up to 10 MB."
    assert policy.help_text("photo") == "JPG or PNG, up to 5 MB."
    assert policy.help_text("report") == "PDF, up to 20 MB."
    assert "export" not in policy.RULES


def test_any_pillow_error_rejects_the_photo(s3, student, monkeypatch):
    def broken_transpose(image: Image.Image) -> Image.Image:
        raise struct.error("unpack requires a buffer of 4 bytes")

    monkeypatch.setattr("apps.files.services.ImageOps.exif_transpose", broken_transpose)
    body = jpeg_with_exif(orientation=6)
    intent = start(student, body, purpose="photo", content_type="image/jpeg")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "image"
    file.refresh_from_db()
    assert file.status == StoredFile.Status.REJECTED
    assert objects(s3) == set()


def test_multi_picture_jpeg_is_accepted(s3, student):
    first = Image.new("RGB", (20, 10), (10, 120, 10))
    second = Image.new("RGB", (8, 4), (0, 0, 0))
    buffer = io.BytesIO()
    first.save(buffer, "MPO", save_all=True, append_images=[second])
    body = buffer.getvalue()
    assert Image.open(io.BytesIO(body)).format == "MPO"
    intent = start(student, body, purpose="photo", content_type="image/jpeg")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    stored = Image.open(io.BytesIO(storage.read_all(file.final_key)))
    assert stored.format == "JPEG"
    assert stored.size == (20, 10)


def test_download_of_a_document_file_audits_its_program(monkeypatch, student):
    from apps.applications.tests.factories import DocumentFileFactory
    from apps.files.tests.factories import StoredFileFactory

    monkeypatch.setattr(storage, "presigned_get", lambda **kwargs: "https://s3/x")
    loose = StoredFileFactory.create(uploaded_by=student)
    services.download_url(user=student, file=loose)
    assert AuditEvent.objects.get(action="file.viewed", target_id=str(loose.id)).program is None
    row = DocumentFileFactory.create(file=StoredFileFactory.create(uploaded_by=student))
    services.download_url(user=student, file=row.file)
    event = AuditEvent.objects.get(action="file.viewed", target_id=str(row.file.id))
    assert event.program == row.document.application.program
    assert event.data == {}


def _fill_recent(user: User, count: int) -> None:
    StoredFile.objects.bulk_create(
        [
            StoredFile(
                uploaded_by=user,
                purpose="document",
                original_name="a.pdf",
                declared_type="application/pdf",
                size=1,
                key=f"k/{uuid.uuid4()}",
            )
            for _ in range(count)
        ]
    )


def test_staff_upload_rate_is_100_an_hour(s3):
    staff = UserFactory.create(verified=True, role=User.Role.STAFF)
    _fill_recent(staff, 20)
    start(staff, b"x" * 10)
    _fill_recent(staff, 100 - 21)
    assert StoredFile.objects.filter(uploaded_by=staff).count() == 100
    with pytest.raises(UploadRejected) as excinfo:
        start(staff, b"x" * 10)
    assert excinfo.value.status == 429
    assert policy.STAFF_STARTS_PER_HOUR == 100


def test_student_upload_rate_still_20(s3, student):
    _fill_recent(student, 20)
    with pytest.raises(UploadRejected) as excinfo:
        start(student, b"x" * 10)
    assert excinfo.value.status == 429


# M9b: the import purpose (CSV and XLSX).

STAFF_CSV = "last_name,first_name\nPe\xf1a,Ana\n".encode("cp1252")


def _staff():
    return UserFactory.create(verified=True, role=User.Role.STAFF)


def _xlsx_bytes() -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["last_name", "first_name"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _confirm_import(body: bytes, content_type: str) -> StoredFile:
    staff = _staff()
    intent = services.start_upload(
        user=staff, purpose="import", name="s.csv", content_type=content_type, size=len(body)
    )
    upload(intent, body)
    return services.confirm_upload(user=staff, file_id=intent.file.id)


def test_import_purpose_phrase():
    assert policy.types_phrase("import") == "CSV or XLSX"
    assert policy.help_text("import") == "CSV or XLSX, up to 2 MB."


def test_import_rule_is_staff_only(s3, student):
    with pytest.raises(UploadRejected) as excinfo:
        services.start_upload(
            user=student, purpose="import", name="s.csv", content_type="text/csv", size=10
        )
    assert excinfo.value.status == 403


def test_csv_declared_as_excel_confirms_as_csv(s3):
    file = _confirm_import(STAFF_CSV, policy.CSV_EXCEL)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == "text/csv"


def test_csv_declared_as_csv_confirms(s3):
    file = _confirm_import(STAFF_CSV, policy.CSV)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == policy.CSV


def test_xls_binary_rejected(s3):
    body = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600
    file = _confirm_import(body, policy.CSV_EXCEL)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "type"


def test_xlsx_confirms(s3):
    file = _confirm_import(_xlsx_bytes(), policy.XLSX)
    assert file.status == StoredFile.Status.READY
    assert file.sniffed_type == policy.XLSX


def test_pdf_declared_as_csv_rejected(s3):
    file = _confirm_import(pdf_bytes(), policy.CSV)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "type"
