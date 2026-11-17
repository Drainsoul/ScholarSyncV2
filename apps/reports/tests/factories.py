from datetime import date

import factory
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import ProgramFactory
from apps.reports.models import Report, ReportFile


def ready_report_file(uploaded_by: User | None = None) -> StoredFile:
    """A ready PDF of the `report` purpose, as a confirmed upload leaves it."""
    kwargs: dict[str, object] = {}
    if uploaded_by is not None:
        kwargs["uploaded_by"] = uploaded_by
    file = StoredFileFactory.create(
        status=StoredFile.Status.READY,
        purpose=StoredFile.Purpose.REPORT,
        original_name="report.pdf",
        sniffed_type="application/pdf",
        sha256="0" * 64,
        **kwargs,
    )
    file.key = file.final_key
    file.save(update_fields=["key"])
    return file


class ReportFactory(factory.django.DjangoModelFactory[Report]):
    class Meta:
        model = Report

    program = factory.declarations.SubFactory(ProgramFactory)
    title = factory.declarations.Sequence(lambda n: f"Report {n}")
    period_start = date(2026, 8, 1)
    period_end = date(2026, 10, 31)
    status = Report.Status.SUBMITTED
    submitted_by = factory.declarations.SubFactory(UserFactory, role=User.Role.STAFF)
    submitted_at = factory.declarations.LazyFunction(timezone.now)


class ReportFileFactory(factory.django.DjangoModelFactory[ReportFile]):
    class Meta:
        model = ReportFile

    report = factory.declarations.SubFactory(ReportFactory)
    file = factory.declarations.LazyAttribute(lambda o: ready_report_file(o.report.submitted_by))
