"""Who may download a report file (M11c)."""

import pytest
from django.http import Http404

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.files import services as file_services
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.selectors import downloadable_file, usable_file
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.reports.tests.factories import ReportFileFactory

pytestmark = pytest.mark.django_db


def _report_file(program_slug: str = "tcu-ceaa") -> tuple[StoredFile, User]:
    program = ProgramFactory.create(slug=program_slug)
    uploader = MembershipFactory.create(program=program).user
    row = ReportFileFactory.create(report__program=program, report__submitted_by=uploader)
    return row.file, uploader


def test_colleague_downloads_after_uploader_removed() -> None:
    file, uploader = _report_file()
    program = file.report_file.report.program
    colleague = MembershipFactory.create(program=program).user
    ProgramMembership.objects.filter(user=uploader).delete()
    assert downloadable_file(colleague, file.pk) == file


def test_other_program_staff_404() -> None:
    file, _uploader = _report_file()
    other = MembershipFactory.create(program=ProgramFactory.create(slug="lani")).user
    with pytest.raises(Http404):
        downloadable_file(other, file.pk)
    student = UserFactory.create()
    with pytest.raises(Http404):
        downloadable_file(student, file.pk)


def test_office_downloads_any_version() -> None:
    file, _uploader = _report_file()
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    assert downloadable_file(office, file.pk) == file


def test_file_viewed_event_has_report_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "presigned_get", lambda **kwargs: "https://s3/x")
    file, uploader = _report_file()
    file_services.download_url(user=uploader, file=file)
    event = AuditEvent.objects.get(action="file.viewed", target_id=str(file.pk))
    assert event.program == file.report_file.report.program


def test_report_file_refused_as_application_document() -> None:
    file, uploader = _report_file()
    assert usable_file(uploader, file.pk, StoredFile.Purpose.DOCUMENT) is None
