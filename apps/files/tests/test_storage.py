from urllib.parse import parse_qs, urlparse

import pytest
import requests

from apps.files import storage


def test_presigned_put_signs_type_and_length(s3):
    url = storage.presigned_put(key="pending/a", content_type="application/pdf", size=10)
    signed = parse_qs(urlparse(url).query)["X-Amz-SignedHeaders"][0].split(";")
    assert {"content-length", "content-type", "host"} <= set(signed)


def test_presign_uses_the_public_endpoint(s3, settings):
    settings.S3_STORAGE = {**settings.S3_STORAGE, "public_endpoint_url": "http://localhost:9999"}
    url = storage.presigned_put(key="pending/a", content_type="image/png", size=1)
    assert url.startswith("http://localhost:9999/")


def test_presign_falls_back_to_the_endpoint(s3, settings):
    settings.S3_STORAGE = {**settings.S3_STORAGE, "public_endpoint_url": ""}
    url = storage.presigned_put(key="pending/a", content_type="image/png", size=1)
    assert url.startswith(settings.S3_STORAGE["endpoint_url"] + "/")


def test_put_head_read_copy_delete_round_trip(s3):
    body = b"0123456789"
    storage.put(key="pending/k", body=body, content_type="application/pdf")
    assert storage.head_size("pending/k") == 10
    assert storage.read_range("pending/k", 4) == b"0123"
    assert storage.read_all("pending/k") == body
    assert b"".join(storage.iter_chunks("pending/k", 3)) == body
    assert storage.copy(source="pending/k", dest="files/k", content_type="application/pdf") is True
    assert storage.read_all("files/k") == body
    assert s3.head_object(Bucket=s3.bucket, Key="files/k")["ContentType"] == "application/pdf"
    storage.delete("pending/k")
    assert storage.head_size("pending/k") is None


def test_missing_objects(s3):
    assert storage.head_size("pending/nope") is None
    assert (
        storage.copy(source="pending/nope", dest="files/x", content_type="application/pdf") is False
    )


def test_reading_a_missing_object_is_unavailable(s3):
    with pytest.raises(storage.StorageUnavailable):
        storage.read_all("pending/nope")
    with pytest.raises(storage.StorageUnavailable):
        storage.read_range("pending/nope", 4)
    with pytest.raises(storage.StorageUnavailable):
        list(storage.iter_chunks("pending/nope"))


def test_presigned_get_downloads_as_attachment(s3):
    storage.put(key="files/d", body=b"hello", content_type="application/octet-stream")
    url = storage.presigned_get(
        key="files/d",
        content_type="application/pdf",
        disposition='attachment; filename="grades.pdf"',
    )
    response = requests.get(url, timeout=10)
    assert response.status_code == 200
    assert response.content == b"hello"
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Content-Disposition"] == 'attachment; filename="grades.pdf"'


def test_presigned_put_upload_works(s3):
    url = storage.presigned_put(key="pending/u", content_type="application/pdf", size=3)
    response = requests.put(
        url, data=b"abc", headers={"Content-Type": "application/pdf"}, timeout=10
    )
    assert response.status_code == 200
    assert storage.head_size("pending/u") == 3


def test_not_configured(settings):
    settings.S3_STORAGE = {**settings.S3_STORAGE, "bucket": ""}
    assert not storage.is_configured()
    with pytest.raises(storage.StorageNotConfigured):
        storage.head_size("x")
    with pytest.raises(storage.StorageNotConfigured):
        storage.presigned_put(key="x", content_type="a/b", size=1)


def test_is_configured_with_blank_endpoint(settings):
    settings.S3_STORAGE = {
        "endpoint_url": "",
        "public_endpoint_url": "",
        "region": "ap-southeast-1",
        "bucket": "b",
        "access_key_id": "k",
        "secret_access_key": "s",
        "addressing_style": "virtual",
    }
    assert storage.is_configured()


def test_unreachable_storage_is_unavailable(settings):
    settings.S3_STORAGE = {
        "endpoint_url": "http://127.0.0.1:9",
        "public_endpoint_url": "",
        "region": "us-east-1",
        "bucket": "b",
        "access_key_id": "k",
        "secret_access_key": "s",
        "addressing_style": "path",
    }
    with pytest.raises(storage.StorageUnavailable):
        storage.head_size("x")
