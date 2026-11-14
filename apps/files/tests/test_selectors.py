from typing import Any

import pytest
from django.http import Http404
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.applications.selectors import staff_can_download, student_can_download
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.files.selectors import downloadable_file, usable_file
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import MembershipFactory

READY = {"status": "ready", "sha256": "a" * 64, "sniffed_type": "image/png"}


@pytest.mark.django_db
def test_usable_file_rules() -> None:
    me = UserFactory.create(verified=True)
    good = StoredFileFactory.create(uploaded_by=me, purpose="photo", **READY)
    assert usable_file(me, str(good.id), "photo") == good
    assert usable_file(me, good.id, "photo") == good
    for bad in [
        StoredFileFactory.create(purpose="photo", **READY),
        StoredFileFactory.create(uploaded_by=me, purpose="photo"),
        StoredFileFactory.create(uploaded_by=me, purpose="document", **READY),
    ]:
        assert usable_file(me, str(bad.id), "photo") is None


@pytest.mark.django_db
@pytest.mark.parametrize("junk", ["not-a-uuid", "", None, 123, object()])
def test_usable_file_never_raises(junk: object) -> None:
    me = UserFactory.create(verified=True)
    assert usable_file(me, junk, "photo") is None


def _submitted_file(version_count: int = 1) -> tuple[Any, list[Any]]:
    application = ApplicationFactory.create(
        status="submitted", submitted_at=timezone.now(), school_name="Some College"
    )
    document = DocumentFactory.create(application=application)
    rows = []
    for number in range(1, version_count + 1):
        rows.append(
            DocumentFileFactory.create(
                document=document, version=number, is_current=number == version_count
            )
        )
    return application, [row.file for row in rows]


@pytest.mark.django_db
def test_staff_of_the_program_can_download_a_submitted_document() -> None:
    application, (file,) = _submitted_file()
    staff = MembershipFactory.create(program=application.program).user
    assert downloadable_file(staff, file.id) == file
    assert staff_can_download(staff, file)


@pytest.mark.django_db
def test_staff_cannot_download_a_draft_document() -> None:
    application = ApplicationFactory.create()
    file = DocumentFileFactory.create(document=DocumentFactory.create(application=application)).file
    staff = MembershipFactory.create(program=application.program).user
    assert not staff_can_download(staff, file)
    with pytest.raises(Http404):
        downloadable_file(staff, file.id)


@pytest.mark.django_db
def test_other_program_staff_get_404() -> None:
    _, (file,) = _submitted_file()
    other = MembershipFactory.create().user
    assert not staff_can_download(other, file)
    with pytest.raises(Http404):
        downloadable_file(other, file.id)
    with pytest.raises(Http404):
        downloadable_file(UserFactory.create(verified=True), file.id)


@pytest.mark.django_db
def test_old_versions_are_downloadable_by_staff() -> None:
    application, files = _submitted_file(version_count=3)
    staff = MembershipFactory.create(program=application.program).user
    for file in files:
        assert downloadable_file(staff, file.id) == file


@pytest.mark.django_db
def test_staff_cannot_download_a_photo() -> None:
    staff = MembershipFactory.create().user
    photo = StoredFileFactory.create(purpose="photo", **READY)
    assert not staff_can_download(staff, photo)
    with pytest.raises(Http404):
        downloadable_file(staff, photo.id)


@pytest.mark.django_db
def test_uploader_and_office_keep_their_access() -> None:
    _, (file,) = _submitted_file()
    assert downloadable_file(file.uploaded_by, file.id) == file
    office = UserFactory.create(role="super_admin")
    assert downloadable_file(office, file.id) == file


def _on_behalf_file() -> tuple[Any, Any]:
    application = ApplicationFactory.create(on_behalf=True)
    row = DocumentFileFactory.create(
        document=DocumentFactory.create(application=application),
        file__uploaded_by=application.created_by,
    )
    return application, row.file


@pytest.mark.django_db
def test_staff_can_download_on_behalf_draft_document() -> None:
    application, file = _on_behalf_file()
    colleague = MembershipFactory.create(program=application.program).user
    assert staff_can_download(colleague, file)
    assert downloadable_file(colleague, file.id) == file


@pytest.mark.django_db
def test_other_program_staff_cannot_download_on_behalf_draft() -> None:
    _, file = _on_behalf_file()
    other = MembershipFactory.create().user
    assert not staff_can_download(other, file)
    with pytest.raises(Http404):
        downloadable_file(other, file.id)


@pytest.mark.django_db
def test_staff_still_cannot_download_student_draft_document() -> None:
    application = ApplicationFactory.create(on_behalf=False)
    file = DocumentFileFactory.create(document=DocumentFactory.create(application=application)).file
    staff = MembershipFactory.create(program=application.program).user
    assert not staff_can_download(staff, file)
    with pytest.raises(Http404):
        downloadable_file(staff, file.id)


@pytest.mark.django_db
def test_student_can_download_staff_uploaded_file_on_own_application(
    django_assert_num_queries,
) -> None:
    application, file = _on_behalf_file()
    student = application.profile.user
    with django_assert_num_queries(1):
        assert student_can_download(student, file)
    assert downloadable_file(student, file.id) == file


@pytest.mark.django_db
def test_student_cannot_download_another_students_document() -> None:
    _, file = _on_behalf_file()
    other = UserFactory.create(verified=True)
    assert not student_can_download(other, file)
    with pytest.raises(Http404):
        downloadable_file(other, file.id)
