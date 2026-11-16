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
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award
from apps.awards.tests.factories import RenewalFactory
from apps.awards.tests.scholars import add_record, make_scholar
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
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
