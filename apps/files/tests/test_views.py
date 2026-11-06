import json
import uuid
from urllib.parse import urlsplit

import pytest
import requests
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.tests.conftest import pdf_bytes
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

INTENT = "files:upload-intent"
COPY_READ = "We couldn't read that upload request."


def post_json(client, name, body, **kwargs):
    data = body if isinstance(body, str) else json.dumps(body)
    return client.post(reverse(name, **kwargs), data=data, content_type="application/json")


def intent_body(pdf: bytes | None = None, **over):
    pdf = pdf_bytes() if pdf is None else pdf
    body = {
        "purpose": "document",
        "name": "grades.pdf",
        "type": "application/pdf",
        "size": len(pdf),
    }
    return {**body, **over}


@pytest.fixture
def student(db):
    return UserFactory.create(verified=True)


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


def upload_ready(client, pdf=None):
    pdf = pdf_bytes() if pdf is None else pdf
    intent = post_json(client, INTENT, intent_body(pdf)).json()
    requests.put(intent["url"], data=pdf, headers=intent["headers"], timeout=10).raise_for_status()
    return intent, client.post(intent["confirm_url"])


def test_intent_returns_presigned_put(signed_in, s3):
    response = post_json(signed_in, INTENT, intent_body())
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "url", "headers", "confirm_url"}
    assert data["confirm_url"] == reverse("files:upload-confirm", kwargs={"file_id": data["id"]})
    assert data["headers"] == {"Content-Type": "application/pdf"}
    assert StoredFile.objects.get(pk=data["id"]).status == StoredFile.Status.PENDING


@pytest.mark.parametrize("body", ["nope", "[1]", '"x"', "null"])
def test_intent_bad_json(signed_in, s3, body):
    response = post_json(signed_in, INTENT, body)
    assert response.status_code == 400
    assert response.json() == {"error": COPY_READ}


@pytest.mark.parametrize(
    "over",
    [{"size": "10"}, {"size": True}, {"size": 1.5}, {"name": 3}, {"purpose": None}, {"type": []}],
)
def test_intent_wrong_field_types(signed_in, s3, over):
    response = post_json(signed_in, INTENT, intent_body(**over))
    assert response.status_code == 400
    assert response.json() == {"error": COPY_READ}


def test_intent_missing_field(signed_in, s3):
    body = intent_body()
    del body["name"]
    assert post_json(signed_in, INTENT, body).status_code == 400


def test_intent_rejection_copy(signed_in, s3):
    response = post_json(signed_in, INTENT, intent_body(type="image/svg+xml"))
    assert response.status_code == 400
    assert response.json() == {"error": "You can upload a PDF, JPG or PNG file here."}


def test_anonymous_posts_get_401_json(client, db):
    for name, kwargs in (
        (INTENT, None),
        ("files:upload-confirm", {"file_id": uuid.uuid4()}),
    ):
        response = client.post(reverse(name, kwargs=kwargs))
        assert response.status_code == 401
        assert response.json() == {"error": "Sign in to upload files."}


def test_get_on_post_endpoints_is_405(signed_in):
    assert signed_in.get(reverse(INTENT)).status_code == 405


def test_full_round_trip(signed_in, s3):
    pdf = pdf_bytes()
    intent, confirm = upload_ready(signed_in, pdf)
    assert confirm.status_code == 200
    data = confirm.json()
    assert set(data) == {"id", "name", "size", "download_url"}
    assert data["name"] == "grades.pdf"
    assert data["size"] == len(pdf)
    assert data["download_url"] == reverse("files:download", kwargs={"file_id": data["id"]})
    download = signed_in.get(data["download_url"])
    assert download.status_code == 302
    assert "no-store" in download["Cache-Control"]
    assert urlsplit(download["Location"]).netloc == urlsplit(intent["url"]).netloc
    assert requests.get(download["Location"], timeout=10).content == pdf


def test_confirm_twice_returns_200_both_times(signed_in, s3):
    _, first = upload_ready(signed_in)
    second = signed_in.post(reverse("files:upload-confirm", kwargs={"file_id": first.json()["id"]}))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_rejected_confirm_returns_400_with_message(signed_in, s3):
    intent = post_json(signed_in, INTENT, intent_body()).json()
    # Nothing is PUT, so the object is missing.
    for _ in range(2):
        response = signed_in.post(intent["confirm_url"])
        assert response.status_code == 400
        assert response.json() == {"error": "We didn't receive your file. Try uploading it again."}


def test_other_student_gets_404(client, signed_in, s3):
    _, confirm = upload_ready(signed_in)
    file_id = confirm.json()["id"]
    client.force_login(UserFactory.create(verified=True))
    response = client.post(reverse("files:upload-confirm", kwargs={"file_id": file_id}))
    assert response.status_code == 404
    assert response.json() == {"error": "Upload not found."}
    assert client.get(reverse("files:download", kwargs={"file_id": file_id})).status_code == 404


def test_unknown_confirm_is_404(signed_in, s3):
    response = signed_in.post(reverse("files:upload-confirm", kwargs={"file_id": uuid.uuid4()}))
    assert response.status_code == 404
    assert response.json() == {"error": "Upload not found."}


def test_office_can_download(client, signed_in, s3):
    _, confirm = upload_ready(signed_in)
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True))
    assert client.get(confirm.json()["download_url"]).status_code == 302


def test_staff_of_any_program_gets_404(client, signed_in, s3):
    _, confirm = upload_ready(signed_in)
    staff = MembershipFactory.create(program=ProgramFactory.create(), user__verified=True).user
    client.force_login(staff)
    assert client.get(confirm.json()["download_url"]).status_code == 404


def test_pending_and_rejected_files_are_not_downloadable(signed_in, student, s3):
    for status in (StoredFile.Status.PENDING, StoredFile.Status.REJECTED):
        file = StoredFileFactory.create(
            uploaded_by=student,
            status=status,
            rejected_reason="missing" if status == StoredFile.Status.REJECTED else "",
        )
        response = signed_in.get(reverse("files:download", kwargs={"file_id": file.id}))
        assert response.status_code == 404


def test_anonymous_download_redirects_to_sign_in(client, db):
    response = client.get(reverse("files:download", kwargs={"file_id": uuid.uuid4()}))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("account_login"))
    assert "next=" in response["Location"]


def test_storage_not_configured_is_503(signed_in, settings):
    settings.S3_STORAGE = {}
    response = post_json(signed_in, INTENT, intent_body())
    assert response.status_code == 503
    assert response.json() == {"error": "File uploads aren't set up on this copy of ScholarSync."}


def test_storage_down_is_503(signed_in, s3, monkeypatch):
    intent = post_json(signed_in, INTENT, intent_body()).json()

    def boom(*args, **kwargs):
        raise storage.StorageUnavailable("down")

    monkeypatch.setattr(storage, "head_size", boom)
    monkeypatch.setattr(storage, "copy", boom)
    response = signed_in.post(intent["confirm_url"])
    assert response.status_code == 503
    assert response.json() == {
        "error": "File storage isn't available right now. Try again in a few minutes."
    }
    assert StoredFile.objects.get(pk=intent["id"]).status == StoredFile.Status.PENDING


def test_download_storage_not_configured_is_503_text(signed_in, student, monkeypatch):
    file = StoredFileFactory.create(
        uploaded_by=student,
        status=StoredFile.Status.READY,
        sniffed_type="application/pdf",
        sha256="a" * 64,
    )

    def boom(*args, **kwargs):
        raise storage.StorageNotConfigured("no")

    monkeypatch.setattr(storage, "presigned_get", boom)
    response = signed_in.get(reverse("files:download", kwargs={"file_id": file.id}))
    assert response.status_code == 503
    assert response["Content-Type"].startswith("text/plain")
    assert response.content.decode() == "File uploads aren't set up on this copy of ScholarSync."
