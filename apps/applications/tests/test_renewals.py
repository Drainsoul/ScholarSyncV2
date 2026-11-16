import html
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse

from apps.accounts.models import User
from apps.applications import renewals
from apps.applications.models import Application
from apps.applications.renewals import (
    ALREADY_RENEWED,
    OTHER_OPEN,
    RENEWAL_NOT_ACTIVE,
    RENEWAL_REJECTED,
    RENEWAL_SUMMER,
    start_renewal,
)
from apps.applications.services import RENEWAL_TIER_GONE, submit_application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.awards.models import Award
from apps.awards.tests.factories import RenewalFactory
from apps.awards.tests.scholars import add_record, make_scholar
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm, BenefitTier, Program, RequiredDocument
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
from apps.students.models import EducationRecord
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


@dataclass
class Scholar:
    previous: AcademicTerm
    current: AcademicTerm
    program: Program
    tier: BenefitTier
    award: Award

    @property
    def user(self) -> User:
        assert self.award.profile.user is not None
        return self.award.profile.user


def scholar_world(term_number: int = 1, **program_fields: object) -> Scholar:
    previous = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=term_number, is_current=True)
    values: dict[str, object] = {
        "renewal_min_gwa_percent": Decimal("80"),
        "renewal_min_units": 15,
    }
    values.update(program_fields)
    program = ProgramFactory.create(**values)
    tier = BenefitTierFactory.create(program=program, effective_from=previous, code="standard")
    RequiredDocumentFactory.create(program=program, code="cor", label="COR", applies_to="renewal")
    RequiredDocumentFactory.create(program=program, code="jhs", label="JHS", applies_to="new")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(
        profile=profile,
        school=None,
        school_name="Factory College",
        school_type="private",
        gwa=Decimal("88.00"),
        gwa_scale="percent",
        units=18,
        year_level=3,
    )
    award = make_scholar(program, tier, [previous], profile=profile)
    return Scholar(previous, current, program, tier, award)


@pytest.fixture
def scholar() -> Scholar:
    return scholar_world()


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


def assert_refused(call: Callable[[], object], message: str) -> None:
    before = Application.objects.count()
    with pytest.raises(ValidationError) as caught:
        call()
    assert caught.value.messages == [message]
    assert Application.objects.count() == before
    assert "application.renewal_started" not in actions()


def test_start_renewal_creates_draft(scholar: Scholar) -> None:
    application = start_renewal(user=scholar.user, award_id=scholar.award.pk)
    assert application.kind == Application.Kind.RENEWAL
    assert application.status == Application.Status.DRAFT
    assert (application.award, application.term) == (scholar.award, scholar.current)
    assert (application.profile, application.program) == (
        scholar.award.profile,
        scholar.program,
    )
    assert application.created_by == scholar.user
    event = AuditEvent.objects.get(action="application.renewal_started")
    assert event.data == {"award": scholar.award.pk}


def test_start_renewal_returns_open_one(scholar: Scholar) -> None:
    first = start_renewal(user=scholar.user, award_id=scholar.award.pk)
    assert start_renewal(user=scholar.user, award_id=scholar.award.pk) == first
    assert Application.objects.count() == 1


def test_start_renewal_not_active(scholar: Scholar) -> None:
    Award.objects.filter(pk=scholar.award.pk).update(status=Award.Status.SUSPENDED)
    assert_refused(
        lambda: start_renewal(user=scholar.user, award_id=scholar.award.pk), RENEWAL_NOT_ACTIVE
    )


def test_start_renewal_summer() -> None:
    world = scholar_world(3)
    assert_refused(lambda: start_renewal(user=world.user, award_id=world.award.pk), RENEWAL_SUMMER)


def test_start_renewal_already_renewed(scholar: Scholar) -> None:
    add_record(scholar.award, scholar.current)
    assert_refused(
        lambda: start_renewal(user=scholar.user, award_id=scholar.award.pk),
        ALREADY_RENEWED.format(term=scholar.current),
    )


def test_start_renewal_rejected(scholar: Scholar) -> None:
    RenewalFactory.create(
        award=scholar.award, term=scholar.current, status=Application.Status.REJECTED
    )
    assert_refused(
        lambda: start_renewal(user=scholar.user, award_id=scholar.award.pk),
        RENEWAL_REJECTED.format(term=scholar.current),
    )


def test_start_renewal_other_open_application(scholar: Scholar) -> None:
    ApplicationFactory.create(
        profile=scholar.award.profile, program=scholar.program, term=scholar.current
    )
    assert_refused(
        lambda: start_renewal(user=scholar.user, award_id=scholar.award.pk),
        OTHER_OPEN.format(program=scholar.program.name),
    )


def test_start_renewal_window_closed() -> None:
    world = scholar_world(applications_close_on=date(2026, 10, 1))
    assert_refused(
        lambda: start_renewal(user=world.user, award_id=world.award.pk),
        "Applications closed on 1 October 2026.",
    )


def test_start_renewal_no_term(scholar: Scholar) -> None:
    AcademicTerm.objects.update(is_current=False)
    AcademicTerm.objects.filter(pk=scholar.current.pk).update(
        starts_on=date(2027, 8, 1), ends_on=date(2027, 12, 31)
    )
    assert_refused(
        lambda: start_renewal(user=scholar.user, award_id=scholar.award.pk),
        "Applications aren't open: the scholarship office hasn't set up the current school term.",
    )


def test_start_renewal_other_students_award_404(scholar: Scholar) -> None:
    other = FullProfileFactory.create().user
    assert other is not None
    with pytest.raises(Http404):
        start_renewal(user=other, award_id=scholar.award.pk)
    assert not AuditEvent.objects.filter(action="application.renewal_started").exists()


def test_start_renewal_race_returns_existing(scholar: Scholar) -> None:
    existing = RenewalFactory.create(award=scholar.award, term=scholar.current)
    from apps.applications.selectors import open_application as real

    calls = {"n": 0}

    def first_none(*args: object, **kwargs: object) -> Application | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)  # type: ignore[arg-type]

    with mock.patch.object(renewals, "renewal_for") as status:
        from apps.awards.selectors import Renewal, RenewalStatus

        status.return_value = Renewal(RenewalStatus.DUE, scholar.current, None)
        with mock.patch.object(renewals, "open_application", side_effect=first_none):
            assert start_renewal(user=scholar.user, award_id=scholar.award.pk) == existing


# --- Submitting a renewal ---


def renewal_ready(world: Scholar) -> Application:
    """A draft renewal with every renewal document uploaded."""
    application = start_renewal(user=world.user, award_id=world.award.pk)
    for requirement in RequiredDocument.objects.filter(program=world.program):
        if requirement.applies_to in ("renewal", "both"):
            document = DocumentFactory.create(application=application, requirement=requirement)
            DocumentFileFactory.create(document=document)
    return application


def test_submit_renewal_freezes_and_snapshots(scholar: Scholar) -> None:
    application = renewal_ready(scholar)
    submitted = submit_application(
        user=scholar.user, application=application, tier=None, declares_no_failing=True
    )
    assert submitted.status == Application.Status.SUBMITTED
    assert submitted.requested_tier == scholar.tier
    assert submitted.declares_no_failing is True
    assert (submitted.school_name, submitted.gwa, submitted.year_level) == (
        "Factory College",
        Decimal("88.00"),
        3,
    )
    codes = [check["code"] for check in submitted.match_snapshot["checks"]]
    assert codes == ["window", "school", "renewal_gwa", "renewal_units"]
    event = AuditEvent.objects.get(action="application.submitted")
    assert event.data == {"tier": "standard"}


def test_submit_renewal_uses_repriced_tier(scholar: Scholar) -> None:
    repriced = BenefitTierFactory.create(
        program=scholar.program, effective_from=scholar.current, code="standard"
    )
    submitted = submit_application(user=scholar.user, application=renewal_ready(scholar), tier=None)
    assert submitted.requested_tier == repriced


def test_submit_renewal_refused_when_rule_unmet(scholar: Scholar) -> None:
    application = renewal_ready(scholar)
    EducationRecord.objects.filter(profile=scholar.award.profile).update(gwa=Decimal("79"))
    with pytest.raises(ValidationError) as caught:
        submit_application(user=scholar.user, application=application, tier=None)
    assert caught.value.messages == [
        "Your GWA of 79.00 doesn't meet this program's renewal minimum of 80%."
    ]
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_submit_renewal_refused_without_declaration() -> None:
    world = scholar_world(renewal_no_failing_grades=True)
    application = renewal_ready(world)
    with pytest.raises(ValidationError) as caught:
        submit_application(user=world.user, application=application, tier=None)
    assert caught.value.messages == [
        "Confirm below that you have no failing, incomplete or dropped subjects."
    ]
    submitted = submit_application(
        user=world.user, application=application, tier=None, declares_no_failing=True
    )
    assert submitted.status == Application.Status.SUBMITTED


def test_submit_renewal_tier_gone(scholar: Scholar) -> None:
    BenefitTierFactory.create(
        program=scholar.program, effective_from=scholar.current, code="standard", is_active=False
    )
    with pytest.raises(ValidationError) as caught:
        submit_application(user=scholar.user, application=renewal_ready(scholar), tier=None)
    assert caught.value.messages == [RENEWAL_TIER_GONE]


def test_renewal_detail_shows_renewal_checks_and_documents(client, scholar: Scholar) -> None:
    application = start_renewal(user=scholar.user, award_id=scholar.award.pk)
    client.force_login(scholar.user)
    response = client.get(reverse("applications:detail", args=[application.pk]))
    body = html.unescape(response.content.decode())
    assert f"Renewal: {scholar.program.name}" in body
    assert f"Renewing your scholarship for {scholar.current}." in body
    assert "To renew: a GWA of at least 80% (schools that grade in percent)." in body
    assert "COR" in body
    assert "JHS" not in body
    assert 'name="tier"' not in body
    assert "declares_no_failing" not in body  # the program doesn't ask


def test_renewal_detail_asks_declaration_when_rule_on(client) -> None:
    world = scholar_world(renewal_no_failing_grades=True)
    application = start_renewal(user=world.user, award_id=world.award.pk)
    client.force_login(world.user)
    body = html.unescape(
        client.get(reverse("applications:detail", args=[application.pk])).content.decode()
    )
    assert "I have no failing, incomplete or dropped subjects this term." in body


def test_renewal_submit_view_passes_declaration(client) -> None:
    world = scholar_world(renewal_no_failing_grades=True)
    application = renewal_ready(world)
    client.force_login(world.user)
    response = client.post(
        reverse("applications:submit", args=[application.pk]),
        {"declaration": "on", "declares_no_failing": "on"},
    )
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert application.declares_no_failing is True


def test_renewal_detail_query_budget(client, scholar: Scholar, django_assert_max_num_queries):
    application = start_renewal(user=scholar.user, award_id=scholar.award.pk)
    client.force_login(scholar.user)
    with django_assert_max_num_queries(14):  # the student detail budget
        assert client.get(reverse("applications:detail", args=[application.pk])).status_code == 200


def test_list_marks_renewal(client, scholar: Scholar) -> None:
    start_renewal(user=scholar.user, award_id=scholar.award.pk)
    client.force_login(scholar.user)
    body = client.get(reverse("applications:list")).content.decode()
    assert "Renewal" in body


@pytest.mark.parametrize("status", [Award.Status.SUSPENDED, Award.Status.INACTIVE])
def test_submit_renewal_refused_when_award_no_longer_active(scholar: Scholar, status: str) -> None:
    application = renewal_ready(scholar)
    Award.objects.filter(pk=scholar.award.pk).update(status=status)
    with pytest.raises(ValidationError) as caught:
        submit_application(user=scholar.user, application=application, tier=None)
    assert caught.value.messages == [RENEWAL_NOT_ACTIVE]
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
