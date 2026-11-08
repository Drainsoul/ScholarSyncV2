import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

URL = "/me/profile/photo/"
ERROR = "Upload the photo again."


@pytest.fixture
def student(db):
    return UserFactory.create(verified=True)


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


def photo_file(user, **overrides):
    values = {
        "uploaded_by": user,
        "purpose": StoredFile.Purpose.PHOTO,
        "status": StoredFile.Status.READY,
        "original_name": "me.png",
        "declared_type": "image/png",
        "sniffed_type": "image/png",
        "sha256": "a" * 64,
    }
    return StoredFileFactory.create(**{**values, **overrides})


def test_url_name():
    assert reverse("students:profile-photo") == URL


def test_get_without_a_photo_shows_the_uploader(signed_in):
    response = signed_in.get(URL)
    html = response.content.decode()
    assert response.status_code == 200
    assert "data-upload-value" in html
    assert "A clear, recent photo of your face. JPG or PNG, up to 5 MB." in html
    assert "Remove photo" not in html
    assert 'alt="Your profile photo"' not in html


def test_get_with_a_photo_shows_it_and_remove(signed_in, student):
    file = photo_file(student)
    ProfileFactory.create(user=student, photo=file)
    html = signed_in.get(URL).content.decode()
    assert f'src="/files/{file.id}/"' in html
    assert 'alt="Your profile photo"' in html
    assert 'width="160" height="160"' in html
    assert "Remove photo" in html


def test_a_ready_own_photo_saves(signed_in, student):
    file = photo_file(student)
    response = signed_in.post(URL, {"photo": str(file.id)})
    assert response.status_code == 302
    assert response.url == reverse("students:profile")
    student.profile.refresh_from_db()
    assert student.profile.photo_id == file.id
    messages = [str(m) for m in response.wsgi_request._messages]
    assert messages == ["Photo saved."]


@pytest.mark.parametrize(
    "make",
    [
        lambda user: photo_file(UserFactory.create(verified=True)),
        lambda user: photo_file(user, status=StoredFile.Status.PENDING),
        lambda user: photo_file(user, purpose=StoredFile.Purpose.DOCUMENT),
        lambda user: photo_file(user, status=StoredFile.Status.REJECTED, rejected_reason="x"),
        lambda user: "not-a-uuid",
        lambda user: "",
    ],
    ids=["someone-else", "pending", "document", "rejected", "garbage", "blank"],
)
def test_unusable_file_is_refused_and_photo_unchanged(signed_in, student, make):
    current = photo_file(student)
    ProfileFactory.create(user=student, photo=current)
    value = make(student)
    response = signed_in.post(URL, {"photo": str(getattr(value, "id", value))})
    assert response.status_code == 200
    assert ERROR in response.content.decode()
    student.profile.refresh_from_db()
    assert student.profile.photo_id == current.id


def test_remove_clears_the_photo(signed_in, student):
    ProfileFactory.create(user=student, photo=photo_file(student))
    response = signed_in.post(URL, {"action": "remove"})
    assert response.status_code == 302
    student.profile.refresh_from_db()
    assert student.profile.photo_id is None
    assert [str(m) for m in response.wsgi_request._messages] == ["Photo removed."]


def test_overview_links_to_the_photo_page(signed_in):
    assert URL in signed_in.get(reverse("students:profile")).content.decode()
