"""Import files leave storage after 7 days (M12)."""

from datetime import timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.awards.tests.factories import ScholarImportFactory
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.selectors import usable_file
from apps.files.tests.factories import StoredFileFactory

pytestmark = pytest.mark.django_db

CSV = "text/csv"
BODY = b"Last name,First name\n"


def _import_file(days_old: int, *, put: bool = True) -> StoredFile:
    file = StoredFileFactory.create(
        purpose=StoredFile.Purpose.IMPORT,
        status=StoredFile.Status.READY,
        declared_type=CSV,
        sniffed_type=CSV,
        sha256="0" * 64,
    )
    file.key = file.final_key
    file.save(update_fields=["key"])
    if put:
        storage.put(key=file.key, body=BODY, content_type=CSV)
    StoredFile.objects.filter(pk=file.pk).update(
        created_at=timezone.now() - timedelta(days=days_old)
    )
    return file


def _keys(s3: Any) -> set[str]:
    listing = s3.list_objects_v2(Bucket=s3.bucket)
    return {item["Key"] for item in listing.get("Contents", [])}


def test_cleanup_deletes_old_import_objects_and_unreferenced_rows(s3: Any) -> None:
    loose = _import_file(8)
    kept = _import_file(8)
    batch = ScholarImportFactory.create(file=kept)
    fresh = _import_file(6)
    call_command("cleanup")
    assert not StoredFile.objects.filter(pk=loose.pk).exists()
    kept.refresh_from_db()
    assert (kept.status, kept.rejected_reason) == (StoredFile.Status.REJECTED, "expired")
    assert _keys(s3) == {fresh.key}
    assert usable_file(kept.uploaded_by, kept.pk, StoredFile.Purpose.IMPORT) is None
    assert usable_file(loose.uploaded_by, loose.pk, StoredFile.Purpose.IMPORT) is None
    assert usable_file(fresh.uploaded_by, fresh.pk, StoredFile.Purpose.IMPORT) == fresh
    batch.refresh_from_db()  # the import record itself stays


def test_cleanup_with_object_already_gone(s3: Any) -> None:
    gone = _import_file(9, put=False)
    call_command("cleanup")
    assert not StoredFile.objects.filter(pk=gone.pk).exists()


def test_cleanup_without_storage_touches_no_import(monkeypatch: pytest.MonkeyPatch) -> None:
    old = _import_file(9, put=False)
    monkeypatch.setattr(storage, "is_configured", lambda: False)
    call_command("cleanup")
    old.refresh_from_db()
    assert old.status == StoredFile.Status.READY


def test_cleanup_keeps_row_when_storage_fails(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    old = _import_file(9)

    def fail(key: str) -> None:
        raise storage.StorageUnavailable("Object storage request failed (test).")

    monkeypatch.setattr(storage, "delete", fail)
    call_command("cleanup")
    old.refresh_from_db()
    assert old.status == StoredFile.Status.READY


def test_cleanup_never_deletes_a_referenced_import_row(s3: Any) -> None:
    kept = _import_file(40)
    ScholarImportFactory.create(file=kept)
    call_command("cleanup")  # marks it expired
    StoredFile.objects.filter(pk=kept.pk).update(updated_at=timezone.now() - timedelta(days=40))
    call_command("cleanup")  # the 30-day rejected purge must skip it (PROTECT)
    assert StoredFile.objects.filter(pk=kept.pk).exists()


def test_cleanup_stops_at_the_first_storage_error(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A storage outage costs one timeout per run, not one per old file (the worker also sends
    email)."""
    first, second = _import_file(9), _import_file(10)
    calls: list[str] = []

    def fail(key: str) -> None:
        calls.append(key)
        raise storage.StorageUnavailable("Object storage request failed (test).")

    monkeypatch.setattr(storage, "delete", fail)
    call_command("cleanup")
    assert len(calls) == 1
    for file in (first, second):
        file.refresh_from_db()
        assert file.status == StoredFile.Status.READY


def test_purge_survives_an_import_created_mid_run(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.awards.models import ScholarImport
    from apps.core.management.commands import cleanup

    file = _import_file(40)
    ScholarImportFactory.create(file=file)
    # The run read the referenced files before that import existed.
    monkeypatch.setattr(ScholarImport.objects, "values_list", lambda *args, **kwargs: [])
    assert cleanup.purge_imports(timezone.now()) == 1
    file.refresh_from_db()
    assert (file.status, file.rejected_reason) == (StoredFile.Status.REJECTED, "expired")
