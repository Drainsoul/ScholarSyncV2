from datetime import datetime
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.applications import review, services
from apps.applications.tests.factories import ApplicationFactory
from apps.applications.tests.test_review import REASON, approvable, staff_of, under_review
from apps.awards.models import Award
from apps.core.templatetags.ui import peso
from apps.money import services as money
from apps.money.models import Disbursement
from apps.money.tests.builders import DAY, head_of, payout
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import EmailOutbox, Notification
from apps.workspace.services import notify

pytestmark = pytest.mark.django_db

AFTER_DAY = datetime(2027, 3, 15, 9, 0, tzinfo=timezone.get_default_timezone())


def test_notify_writes_a_notification_and_an_email() -> None:
    user = UserFactory.create()
    row = notify(
        user=user,
        kind="application_received",
        title="T",
        url="/me/applications/1/",
        email_context={"full_name": "A", "program_name": "LANI", "application_url": "x"},
    )
    assert Notification.objects.get() == row
    assert (row.recipient, row.kind, row.title, row.url, row.read_at) == (
        user,
        "application_received",
        "T",
        "/me/applications/1/",
        None,
    )
    mail = EmailOutbox.objects.get()
    assert (mail.to, mail.kind) == (user.email, "application_received")


def test_notify_without_email_context_sends_no_email() -> None:
    notify(user=UserFactory.create(), kind="application_received", title="T")
    assert Notification.objects.count() == 1
    assert not EmailOutbox.objects.exists()


def test_long_titles_are_truncated() -> None:
    row = notify(user=UserFactory.create(), kind="x", title="a" * 300, body="b" * 600)
    assert len(row.title) == 200 and row.title.endswith("…")
    assert len(row.body) == 500 and row.body.endswith("…")


def test_submit_notifies_the_student() -> None:
    application = ApplicationFactory.create()
    services.received_email(application.profile, application)
    row = Notification.objects.get()
    assert row.recipient == application.profile.user
    assert row.title == f"We received your {application.program.name} application"
    assert row.body == "We'll email you when it's reviewed."
    assert row.url == reverse("applications:detail", args=[application.pk])
    assert EmailOutbox.objects.get().kind == "application_received"


def test_return_and_decisions_notify_without_the_reason() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    returned = under_review(program)
    review.return_application(actor=actor, program=program, application=returned, reason=REASON)
    rejected = under_review(program)
    review.reject_application(actor=actor, program=program, application=rejected, reason=REASON)
    approved = approvable(program)
    review.approve_application(actor=actor, program=program, application=approved, tier=None)
    rows = {row.url: row for row in Notification.objects.all()}
    name = program.name
    expected = {
        returned: (f"{name} returned your application", "Open it to see what to fix."),
        rejected: (f"Your {name} application was not approved", "Open it to see the reason."),
        approved: (f"Your {name} application was approved", ""),
    }
    for application, (title, body) in expected.items():
        row = rows[reverse("applications:detail", args=[application.pk])]
        assert (row.title, row.body) == (title, body)
        assert REASON not in row.title + row.body
        assert row.recipient == application.profile.user
    assert EmailOutbox.objects.count() == 3


def test_allowance_notifications(time_machine: object) -> None:
    row = payout(distribution_date=DAY, claim_location="TCU Gymnasium")
    head = head_of(row.schedule.program)
    kwargs: dict[str, Any] = {
        "actor": head,
        "program": row.schedule.program,
        "schedule_id": row.schedule_id,
        "disbursement_id": row.pk,
    }
    money.approve(**kwargs)
    time_machine.move_to(AFTER_DAY)  # type: ignore[attr-defined]
    money.release(**kwargs)
    program = row.schedule.program.name
    ready, released = Notification.objects.order_by("pk")
    amount = peso(row.amount)
    assert ready.title == f"Your {program} allowance is ready to claim"
    assert ready.body == (
        f"{amount} for {row.schedule.term}. Claim it on 14 March 2027 at TCU Gymnasium."
    )
    assert released.title == f"Your {program} allowance was released"
    assert released.body == f"{amount} for {row.schedule.term}."
    assert ready.url == released.url == reverse("scholarships:list")


def test_walk_in_gets_no_notification(time_machine: object) -> None:
    row = payout()
    profile = row.scholar_term.award.profile
    profile.user = None
    profile.save()
    head = head_of(row.schedule.program)
    kwargs: dict[str, Any] = {
        "actor": head,
        "program": row.schedule.program,
        "schedule_id": row.schedule_id,
        "disbursement_id": row.pk,
    }
    money.approve(**kwargs)
    time_machine.move_to(AFTER_DAY)  # type: ignore[attr-defined]
    money.release(**kwargs)
    assert row.__class__.objects.get(pk=row.pk).status == Disbursement.Status.RELEASED
    assert not Notification.objects.exists()
    assert not EmailOutbox.objects.exists()


def test_bulk_approve_refused_row_gets_nothing() -> None:
    first = payout()
    held = payout(first.schedule, award_status=Award.Status.SUSPENDED)
    last = payout(first.schedule)
    result = money.bulk(
        actor=head_of(first.schedule.program),
        program=first.schedule.program,
        schedule_id=first.schedule_id,
        action="approve",
        ids=[first.pk, held.pk, last.pk],
    )
    assert result.done == 2
    recipients = set(Notification.objects.values_list("recipient", flat=True))
    users = {row.scholar_term.award.profile.user_id for row in (first, last)}
    assert recipients == users
    assert set(EmailOutbox.objects.values_list("to", flat=True)) == {
        row.scholar_term.award.profile.user.email  # type: ignore[union-attr]
        for row in (first, last)
    }
    assert held.scholar_term.award.profile.user_id not in recipients
