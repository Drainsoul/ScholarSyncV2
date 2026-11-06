import uuid

import pytest
from django.db import IntegrityError

from apps.files.models import StoredFile, pending_key
from apps.files.tests.factories import StoredFileFactory


def test_ids_are_uuids_and_final_key_uses_purpose(db):
    f = StoredFileFactory.create(purpose=StoredFile.Purpose.PHOTO)
    assert isinstance(f.id, uuid.UUID)
    assert f.final_key == f"files/photo/{f.id}"
    assert pending_key(f.id) == f"pending/{f.id}"


@pytest.mark.parametrize("field,value", [("status", "lost"), ("purpose", "virus")])
def test_choices_are_constrained(db, field, value):
    with pytest.raises(IntegrityError):
        StoredFileFactory.create(**{field: value})


def test_ready_needs_hash_and_sniffed_type(db):
    with pytest.raises(IntegrityError):
        StoredFileFactory.create(status=StoredFile.Status.READY, sha256="", sniffed_type="")


def test_rejected_needs_a_reason(db):
    with pytest.raises(IntegrityError):
        StoredFileFactory.create(status=StoredFile.Status.REJECTED, rejected_reason="")


def test_moto_bucket_fixture_round_trips(s3):
    s3.put_object(Bucket=s3.bucket, Key="x", Body=b"hi")
    assert s3.get_object(Bucket=s3.bucket, Key="x")["Body"].read() == b"hi"
