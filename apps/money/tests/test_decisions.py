from datetime import date, datetime
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.awards.models import Award, ScholarTerm
from apps.awards.services import change_status
from apps.core.models import AuditEvent
from apps.core.transitions import InvalidTransition
from apps.money import services
from apps.money.models import Disbursement
from apps.money.tests.builders import DAY, head_of, payout, staff_of
from apps.money.tests.factories import DisbursementFactory, ScheduleFactory
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

APPROVED = Disbursement.Status.APPROVED
AFTER_DAY = datetime(2027, 3, 15, 9, 0, tzinfo=timezone.get_default_timezone())


def _act(name: str, row: Disbursement, **kwargs: Any) -> Disbursement:
    actor = kwargs.pop("actor", None) or head_of(row.schedule.program)
    result: Disbursement = getattr(services, name)(
        actor=actor,
        program=row.schedule.program,
        schedule_id=row.schedule_id,
        disbursement_id=row.pk,
        **kwargs,
    )
    return result


def _unchanged(row: Disbursement, events: int = 0, mails: int = 0) -> None:
    """The row kept its status, and no audit event or email beyond the given counts appeared."""
    before = row.status
    row.refresh_from_db()
    assert row.status == before
    assert AuditEvent.objects.filter(action__startswith="disbursement.").count() == events
    assert EmailOutbox.objects.count() == mails


def test_approve_sets_approver_and_emails() -> None:
    row = payout(distribution_date=DAY, claim_location="TCU Gymnasium")
    head = head_of(row.schedule.program)
    row = _act("approve", row, actor=head)
    assert (row.status, row.approved_by) == (APPROVED, head)
    assert row.approved_at is not None
    mail = EmailOutbox.objects.get()
    assert mail.kind == "allowance_approved"
    profile = row.scholar_term.award.profile
    assert profile.user is not None
    assert mail.to == profile.user.email
    assert mail.context == {
        "full_name": profile.full_name,
        "program_name": row.schedule.program.name,
        "term_label": str(row.schedule.term),
        "amount": "₱5,000.00",
        "claim_date": "14 March 2027",
        "claim_location": "TCU Gymnasium",
        "scholarships_url": mail.context["scholarships_url"],
    }
    assert mail.context["scholarships_url"].endswith("/me/scholarships/")
    event = AuditEvent.objects.get(action="disbursement.approved")
    assert event.data == {"from": "pending", "to": "approved", "amount": "5000.00"}


def test_staff_cannot_approve() -> None:
    row = payout()
    with pytest.raises(PermissionDenied):
        _act("approve", row, actor=staff_of(row.schedule.program))


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ({"is_published": False}, "Publish the schedule first."),
        ({"award_status": Award.Status.SUSPENDED}, "This scholar's award is suspended."),
        ({"compliance": ScholarTerm.Compliance.INCOMPLETE}, "Check this scholar's documents for"),
    ],
)
def test_approve_refuses(setup: dict[str, Any], message: str) -> None:
    row = payout(**setup)
    with pytest.raises(ValidationError, match=message):
        _act("approve", row)
    _unchanged(row)


def test_reject_needs_a_reason() -> None:
    row = payout()
    with pytest.raises(ValidationError, match="Give a reason."):
        _act("reject", row, reason="   ")
    _unchanged(row)


def test_reject_reason_over_1000_is_refused() -> None:
    row = payout()
    with pytest.raises(ValidationError, match="Keep the reason under 1,000 characters."):
        _act("reject", row, reason="x" * 1001)


def test_reject_keeps_reason_out_of_audit() -> None:
    row = _act("reject", payout(), reason="Did not show up.")
    assert row.decision_reason == "Did not show up."
    event = AuditEvent.objects.get(action="disbursement.rejected")
    assert "Did not show up." not in str(event.data)
    assert not EmailOutbox.objects.exists()


def test_release_before_distribution_day_is_refused(time_machine: Any) -> None:
    time_machine.move_to(
        datetime(2027, 3, 13, 9, 0, tzinfo=timezone.get_default_timezone()), tick=False
    )
    row = payout(distribution_date=DAY, status=APPROVED)
    with pytest.raises(ValidationError, match="Release after the distribution day, 14 March 2027."):
        _act("release", row)
    _unchanged(row)


def test_release_sets_released_at_and_emails(time_machine: Any) -> None:
    time_machine.move_to(AFTER_DAY, tick=False)
    row = _act("release", payout(distribution_date=DAY, status=APPROVED))
    assert row.status == Disbursement.Status.RELEASED
    assert row.released_at == AFTER_DAY
    mail = EmailOutbox.objects.get()
    assert mail.kind == "allowance_released"
    assert set(mail.context) == {
        "full_name",
        "program_name",
        "term_label",
        "amount",
        "scholarships_url",
    }


def test_release_after_hold_is_refused(time_machine: Any) -> None:
    time_machine.move_to(AFTER_DAY, tick=False)
    row = _act("approve", payout(distribution_date=DAY))
    award = row.scholar_term.award
    change_status(
        actor=head_of(award.program),
        program=award.program,
        award=award,
        to=Award.Status.SUSPENDED,
        reason="Waiting for the registrar.",
    )
    with pytest.raises(ValidationError, match="This scholar's award is suspended."):
        _act("release", row)
    _unchanged(row, events=1, mails=1)  # only the approval's


def test_revert_approved_clears_approval() -> None:
    row = _act("revert", _act("approve", payout()))
    assert row.status == Disbursement.Status.PENDING
    assert (row.approved_by, row.approved_at, row.decision_reason) == (None, None, "")
    assert AuditEvent.objects.filter(action="disbursement.reverted").count() == 1


def test_revert_rejected_clears_reason() -> None:
    row = _act("revert", _act("reject", payout(), reason="No ID."))
    assert (row.status, row.decision_reason) == (Disbursement.Status.PENDING, "")


def test_revert_released_is_refused() -> None:
    with pytest.raises(InvalidTransition):
        _act("revert", payout(status=Disbursement.Status.RELEASED))


def test_revert_rejected_with_live_row_elsewhere_is_refused() -> None:
    row = payout(status=Disbursement.Status.REJECTED)
    other = ScheduleFactory.create(program=row.schedule.program, term=row.schedule.term)
    DisbursementFactory.create(scholar_term=row.scholar_term, schedule=other)
    with pytest.raises(
        ValidationError, match=f"This scholar already has a payout for {row.schedule.term}."
    ):
        _act("revert", row)
    _unchanged(row)


def test_no_email_for_profile_without_user() -> None:
    row = payout()
    profile = row.scholar_term.award.profile
    profile.user = None
    profile.save()
    _act("approve", row)
    assert not EmailOutbox.objects.exists()


def test_other_schedule_row_is_404() -> None:
    from django.http import Http404

    row = payout()
    other = ScheduleFactory.create(program=row.schedule.program)
    with pytest.raises(Http404):
        services.approve(
            actor=head_of(row.schedule.program),
            program=row.schedule.program,
            schedule_id=other.pk,
            disbursement_id=row.pk,
        )


def _bulk(schedule: Any, action: str, ids: list[int] | None) -> services.BulkResult:
    return services.bulk(
        actor=head_of(schedule.program),
        program=schedule.program,
        schedule_id=schedule.pk,
        action=action,  # type: ignore[arg-type]
        ids=ids,
    )


def test_bulk_skips_and_reports() -> None:
    good = payout()
    schedule = good.schedule
    held = payout(schedule, award_status=Award.Status.SUSPENDED)
    done = payout(schedule, status=APPROVED)
    result = _bulk(schedule, "approve", [good.pk, held.pk, done.pk])
    assert result.done == 1
    names = {name for name, _ in result.skipped}
    assert names == {
        held.scholar_term.award.profile.full_name,
        done.scholar_term.award.profile.full_name,
    }
    assert "This scholar's award is suspended." in dict(result.skipped).values()


def test_bulk_all_caps_at_500() -> None:
    first = payout()
    payout(first.schedule)
    payout(first.schedule)
    with mock.patch.object(services, "MAX_ALL", 2):
        result = _bulk(first.schedule, "approve", None)
    assert (result.done, result.remaining) == (2, 1)


def test_bulk_ids_outside_schedule_are_skipped() -> None:
    row = payout()
    stranger = payout()
    result = _bulk(row.schedule, "approve", [row.pk, stranger.pk])
    assert result.done == 1
    assert result.skipped == [("", "This payout isn't in this schedule.")]


def test_bulk_too_many_ids() -> None:
    row = payout()
    with pytest.raises(ValidationError, match="Choose at most 100 payouts at a time."):
        _bulk(row.schedule, "approve", list(range(1, 102)))


def test_bulk_needs_a_head() -> None:
    row = payout()
    with pytest.raises(PermissionDenied):
        services.bulk(
            actor=staff_of(row.schedule.program),
            program=row.schedule.program,
            schedule_id=row.schedule_id,
            action="approve",
            ids=[row.pk],
        )


def test_bulk_approve_query_count(django_assert_max_num_queries: Any) -> None:
    first = payout()
    rows = [first] + [payout(first.schedule) for _ in range(49)]
    head = head_of(first.schedule.program)
    with django_assert_max_num_queries(500):  # +50: notifications (M11)
        result = services.bulk(
            actor=head,
            program=first.schedule.program,
            schedule_id=first.schedule_id,
            action="approve",
            ids=[row.pk for row in rows],
        )
    assert result.done == 50


def test_claim_date_format() -> None:
    assert services.long_date(date(2027, 3, 4)) == "4 March 2027"


def test_bulk_all_does_not_count_refused_rows_as_more_to_go() -> None:
    first = payout()
    payout(first.schedule)
    payout(first.schedule, award_status=Award.Status.SUSPENDED)  # stays prepared, refused
    result = _bulk(first.schedule, "approve", None)
    assert (result.done, len(result.skipped), result.remaining) == (2, 1, 0)


def test_bulk_refuses_an_unpublished_schedule_once() -> None:
    first = payout(is_published=False)
    payout(first.schedule)
    with pytest.raises(ValidationError, match="Publish the schedule first.") as exc:
        _bulk(first.schedule, "approve", None)
    assert exc.value.messages == ["Publish the schedule first."]
    assert not Disbursement.objects.filter(status=APPROVED).exists()


def test_bulk_refuses_release_before_the_day_once(time_machine: Any) -> None:
    time_machine.move_to(datetime(2027, 3, 13, 9, 0, tzinfo=timezone.get_default_timezone()))
    first = payout(distribution_date=DAY, status=APPROVED)
    second = payout(first.schedule, status=APPROVED)
    for ids in (None, [first.pk, second.pk]):
        with pytest.raises(ValidationError, match="Release after the distribution day"):
            _bulk(first.schedule, "release", ids)


def test_bulk_approve_notifies_each_row_once() -> None:
    """50 approvals queue exactly 50 emails and 50 notifications (M11)."""
    from apps.workspace.models import Notification

    first = payout()
    rows = [first] + [payout(first.schedule) for _ in range(49)]
    result = _bulk(first.schedule, "approve", [row.pk for row in rows])
    assert result.done == 50
    assert Notification.objects.filter(kind="allowance_approved").count() == 50
    assert EmailOutbox.objects.filter(kind="allowance_approved").count() == 50


def test_bulk_row_failing_after_its_save_rolls_back_whole() -> None:
    """A row that fails at notify, after its status was saved, keeps nothing: no status change,
    no notification, no email, no audit event. The rows around it go through."""
    from apps.workspace import services as workspace
    from apps.workspace.models import Notification

    first = payout()
    middle = payout(first.schedule)
    last = payout(first.schedule)
    victim = middle.scholar_term.award.profile.user
    real = workspace.notify

    def failing(**kwargs: Any) -> Any:
        if kwargs["user"] == victim:
            raise ValidationError("Mail is down.")
        return real(**kwargs)

    with mock.patch.object(services, "notify", failing):
        result = _bulk(first.schedule, "approve", [first.pk, middle.pk, last.pk])
    assert result.done == 2
    middle.refresh_from_db()
    assert middle.status == Disbursement.Status.PENDING
    assert not Notification.objects.filter(recipient=victim).exists()
    assert not EmailOutbox.objects.filter(to=victim.email).exists()  # type: ignore[union-attr]
    approved = AuditEvent.objects.filter(action="disbursement.approved")
    assert set(approved.values_list("target_id", flat=True)) == {str(first.pk), str(last.pk)}


def test_bulk_release_query_count(time_machine: Any, django_assert_max_num_queries: Any) -> None:
    from apps.workspace.models import Notification

    first = payout(status=APPROVED, distribution_date=DAY)
    rows = [first] + [payout(first.schedule, status=APPROVED) for _ in range(49)]
    time_machine.move_to(AFTER_DAY)
    head = head_of(first.schedule.program)
    with django_assert_max_num_queries(500):  # +50: notifications (M11)
        result = services.bulk(
            actor=head,
            program=first.schedule.program,
            schedule_id=first.schedule_id,
            action="release",
            ids=[row.pk for row in rows],
        )
    assert result.done == 50
    assert Notification.objects.filter(kind="allowance_released").count() == 50
