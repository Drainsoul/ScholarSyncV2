"""Report file previews on the staff and office report pages (spec §12 rev 27)."""

import re
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.reports.tests.factories import ReportFileFactory

pytestmark = pytest.mark.django_db

STORAGE = {  # presigning is local: no server needed
    "endpoint_url": "http://127.0.0.1:9",
    "public_endpoint_url": "http://127.0.0.1:9",
    "region": "us-east-1",
    "bucket": "preview",
    "access_key_id": "test",
    "secret_access_key": "test",
    "addressing_style": "path",
}


def test_staff_report_page_previews_its_pdf(client: Any, settings: Any) -> None:
    settings.S3_STORAGE = STORAGE
    program = ProgramFactory.create(slug="tcu-ceaa")
    client.force_login(MembershipFactory.create(program=program).user)
    row = ReportFileFactory.create(report__program=program)
    report = row.report
    url = reverse(
        "reports:file-preview", kwargs={"program": "tcu-ceaa", "pk": report.pk, "file": row.pk}
    )
    detail = client.get(reverse("reports:detail", kwargs={"program": "tcu-ceaa", "pk": report.pk}))
    assert f'href="{url}" hx-get="{url}"' in detail.content.decode()
    fragment = client.get(url, HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in fragment and "data-pdf-preview" in fragment
    src = re.search(r'data-src="([^"]+)"', fragment)
    assert src is not None and "X-Amz-Signature" in src.group(1)
    assert AuditEvent.objects.get(action="file.viewed").program == program
    assert "<html" in client.get(url).content.decode()


def test_office_report_page_previews_its_pdf(client: Any, settings: Any) -> None:
    settings.S3_STORAGE = STORAGE
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
    row = ReportFileFactory.create()
    url = reverse("office:report-file-preview", kwargs={"pk": row.report.pk, "file": row.pk})
    detail = client.get(reverse("office:report-detail", kwargs={"pk": row.report.pk}))
    assert f'href="{url}" hx-get="{url}"' in detail.content.decode()
    assert "data-pdf-preview" in client.get(url, HTTP_HX_REQUEST="true").content.decode()


def test_another_programs_or_reports_file_is_404(client: Any) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa")
    client.force_login(MembershipFactory.create(program=program).user)
    foreign = ReportFileFactory.create()  # another program's report
    mine = ReportFileFactory.create(report__program=program)
    for pk, file in ((foreign.report.pk, foreign.pk), (mine.report.pk, foreign.pk)):
        url = reverse(
            "reports:file-preview", kwargs={"program": "tcu-ceaa", "pk": pk, "file": file}
        )
        assert client.get(url).status_code == 404
