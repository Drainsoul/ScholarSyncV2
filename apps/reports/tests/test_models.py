"""The report table: statuses and the rev 33 backfill."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.reports.models import Report
from apps.reports.tests.factories import ReportFactory


@pytest.mark.django_db
def test_status_constraint_takes_the_head_statuses_and_refuses_others() -> None:
    for status in ("with_head", "approved", "submitted", "accepted", "returned"):
        assert ReportFactory.create(status=status).status == status
    report = ReportFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.filter(pk=report.pk).update(status="lost")


@pytest.mark.django_db
def test_factory_sends_only_reports_past_the_head() -> None:
    assert ReportFactory.create(status="with_head").sent_at is None
    assert ReportFactory.create(status="approved").sent_by is None
    sent = ReportFactory.create()
    assert (sent.sent_by, sent.sent_at) == (sent.submitted_by, sent.submitted_at)


@pytest.mark.django_db(transaction=True)
def test_backfill_marks_existing_reports_sent() -> None:
    before = [("reports", "0001_initial")]
    after = [("reports", "0002_head_review")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        old = executor.loader.project_state(before).apps
        user = old.get_model("accounts", "User").objects.create(
            email="writer@example.com", role="staff"
        )
        program = old.get_model("programs", "Program").objects.create(slug="bf", name="Backfill")
        sent_at = timezone.now()
        row = old.get_model("reports", "Report").objects.create(
            program=program,
            title="Old report",
            period_start="2026-08-01",
            period_end="2026-10-31",
            status="accepted",
            submitted_by=user,
            submitted_at=sent_at,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new = executor.loader.project_state(after).apps.get_model("reports", "Report")
        migrated = new.objects.get(pk=row.pk)
        assert (migrated.sent_by_id, migrated.sent_at) == (user.pk, sent_at)
        assert migrated.head_reviewed_by_id is None and migrated.head_reviewed_at is None
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
