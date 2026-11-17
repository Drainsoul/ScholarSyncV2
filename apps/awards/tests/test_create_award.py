from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.utils import timezone

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarImport, ScholarTerm
from apps.awards.selectors import program_profiles, start_tier
from apps.awards.services import (
    FUTURE_TERM,
    NO_CURRENT_TERM,
    TIER_NOT_OFFERED,
    AwardData,
    TermData,
    already_holds,
    create_award,
)
from apps.awards.tests.factories import ScholarImportFactory
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.tests.factories import FullProfileFactory, ProfileFactory

pytestmark = pytest.mark.django_db


class World:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program = ProgramFactory.create(merit_min_gwa_percent=Decimal("90.00"))
        self.tier = BenefitTierFactory.create(
            program=self.program, effective_from=self.current, code="standard"
        )
        self.actor = MembershipFactory.create(program=self.program).user
        self.profile = FullProfileFactory.create(
            user=None, created_for=self.program, created_by=self.actor
        )

    def data(self, term: AcademicTerm | None = None, **record: Any) -> AwardData:
        values: dict[str, Any] = {
            "term": term or self.current,
            "school": None,
            "school_name": "Walk-in College",
            "school_type": "private",
            "gwa_scale": "percent",
            "course": "BSED",
            "year_level": 2,
            "gwa": Decimal("92.00"),
            "units": 18,
            "compliance_checked": False,
        }
        values.update(record)
        return AwardData(
            tier_code="standard",
            student_number="2026-001",
            notes="Walk-in.",
            record=TermData(**values),
        )

    def create(self, data: AwardData | None = None, **kwargs: Any) -> Award:
        options: dict[str, Any] = {
            "actor": self.actor,
            "program": self.program,
            "profile_id": self.profile.pk,
            "data": data or self.data(),
            "source": Award.Source.MANUAL,
        }
        options.update(kwargs)
        return create_award(**options)


@pytest.fixture
def world() -> World:
    return World()


def test_creates_manual_award_and_record(world: World) -> None:
    award = world.create()
    assert (award.status, award.source, award.started_term, award.tier) == (
        "active",
        "manual",
        world.current,
        world.tier,
    )
    assert (award.student_number, award.notes, award.import_batch) == ("2026-001", "Walk-in.", None)
    [record] = ScholarTerm.objects.filter(award=award)
    assert (record.term, record.school_name, record.gwa, record.units, record.tier) == (
        world.current,
        "Walk-in College",
        Decimal("92.00"),
        18,
        world.tier,
    )
    assert record.merit is True  # 92 meets the program's 90 merit rule
    assert record.compliance == ScholarTerm.Compliance.INCOMPLETE
    [event] = AuditEvent.objects.filter(action="award.created")
    assert event.data == {
        "source": "manual",
        "tier": "standard",
        "term": world.current.pk,
        "record": record.pk,
    }
    assert event.program == world.program


def test_compliance_checked(world: World) -> None:
    award = world.create(world.data(compliance_checked=True))
    assert award.terms.get().compliance == ScholarTerm.Compliance.COMPLETE


def test_refuses_holder(world: World) -> None:
    make_scholar(
        world.program,
        world.tier,
        [world.previous],
        profile=world.profile,
        status=Award.Status.SUSPENDED,
    )
    with pytest.raises(ValidationError) as caught:
        world.create()
    assert caught.value.messages == [already_holds(world.program)]
    assert Award.objects.count() == 1
    assert not AuditEvent.objects.filter(action="award.created").exists()


def test_refuses_future_term(world: World) -> None:
    future = AcademicTermFactory.create(school_year_start=2026, term=2)
    with pytest.raises(ValidationError) as caught:
        world.create(world.data(future))
    assert caught.value.messages == [FUTURE_TERM]
    assert not Award.objects.exists()


def test_refuses_without_current_term(world: World) -> None:
    AcademicTerm.objects.update(is_current=False)
    with pytest.raises(ValidationError) as caught:
        world.create()
    assert caught.value.messages == [NO_CURRENT_TERM]


def test_refuses_tier_not_in_force(world: World) -> None:
    data = world.data()
    data = AwardData(tier_code="premier", student_number="", notes="", record=data.record)
    with pytest.raises(ValidationError) as caught:
        world.create(data)
    assert caught.value.messages == [TIER_NOT_OFFERED.format(code="premier", term=world.current)]


def test_back_dated_start_uses_earliest_tier(world: World) -> None:
    award = world.create(world.data(world.previous))
    assert award.tier == world.tier
    assert award.started_term == world.previous
    assert award.terms.get().tier == world.tier


def test_in_force_tier_wins_over_earliest(world: World) -> None:
    repriced = BenefitTierFactory.create(
        program=world.program,
        effective_from=AcademicTermFactory.create(school_year_start=2025, term=3),
        code="standard",
    )
    # In force for the current term is the current-term row (latest effective by then).
    assert start_tier(world.program, "standard", world.current) == world.tier
    # The summer-2025 row is the only one in force for summer 2025 and later until 2026-1.
    summer = AcademicTerm.objects.get(school_year_start=2025, term=3)
    assert start_tier(world.program, "standard", summer) == repriced
    # Nothing in force for 2025-2: the earliest row (summer 2025) is used.
    assert start_tier(world.program, "standard", world.previous) == repriced


def test_profile_outside_program_404(world: World) -> None:
    stranger = ProfileFactory.create()
    with pytest.raises(Http404):
        world.create(profile_id=stranger.pk)
    assert not Award.objects.exists()


def test_inactive_program_404(world: World) -> None:
    world.program.is_active = False
    world.program.save()
    with pytest.raises(Http404):
        world.create()


def test_other_staff_403(world: World) -> None:
    outsider = MembershipFactory.create().user
    with pytest.raises(PermissionDenied):
        world.create(actor=outsider)


def test_imported_award_links_batch(world: World) -> None:
    batch = ScholarImportFactory.create(program=world.program, imported_by=world.actor)
    award = world.create(source=Award.Source.IMPORTED, batch=batch)
    assert award.source == "imported"
    assert award.import_batch == batch
    assert list(batch.awards.all()) == [award]
    assert AuditEvent.objects.get(action="award.created").data["source"] == "imported"


def test_program_profiles(world: World) -> None:
    holder = make_scholar(world.program, world.tier, [world.previous]).profile
    applicant = ApplicationFactory.create(
        program=world.program,
        term=world.current,
        status=Application.Status.SUBMITTED,
        submitted_at=timezone.now(),
    ).profile
    drafter = ApplicationFactory.create(program=world.program, term=world.current).profile
    other_program = FullProfileFactory.create(user=None, created_for=ProgramFactory.create())
    unrelated = ProfileFactory.create()
    # A second award and a second application must not duplicate the holder.
    ApplicationFactory.create(
        profile=holder,
        program=world.program,
        term=world.current,
        status=Application.Status.SUBMITTED,
        submitted_at=timezone.now(),
    )
    rows = list(program_profiles(world.program))
    assert sorted(p.pk for p in rows) == sorted([world.profile.pk, holder.pk, applicant.pk])
    assert drafter not in rows
    assert other_program not in rows
    assert unrelated not in rows


def test_scholar_import_str(world: World) -> None:
    batch = ScholarImportFactory.create(program=world.program, imported_by=world.actor)
    assert str(batch) == f"Scholar import {batch.pk}"
    assert isinstance(batch, ScholarImport)
