from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.matching.selectors import eligibility_for, match_page
from apps.programs.tests.factories import (
    AcademicTermFactory,
    ProgramFactory,
    SchoolFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


def user_of(profile: StudentProfile) -> User:
    assert profile.user is not None
    return profile.user


@pytest.fixture
def term():
    return AcademicTermFactory.create(school_year_start=2026, is_current=True)


def test_match_page_without_profile_creates_nothing(term):
    user = UserFactory.create()
    page = match_page(user, today=TODAY)
    assert StudentProfile.objects.count() == 0
    assert page.profile is None
    assert page.hint is None
    assert page.matches == []


def test_match_page_lists_active_programs_only(term):
    ProgramFactory.create(name="Bravo")
    ProgramFactory.create(name="Alpha")
    ProgramFactory.create(name="Hidden", is_active=False)
    profile = FullProfileFactory.create()
    page = match_page(user_of(profile), today=TODAY)
    assert [m.program.name for m in page.matches] == ["Alpha", "Bravo"]
    assert page.term == term


def test_open_application_id_set_for_open_draft_only(term):
    program = ProgramFactory.create()
    other = ProgramFactory.create()
    profile = FullProfileFactory.create()
    draft = ApplicationFactory.create(profile=profile, program=program, term=term)
    ApplicationFactory.create(
        profile=profile, program=other, term=term, status=Application.Status.WITHDRAWN
    )
    page = match_page(user_of(profile), today=TODAY)
    by_slug = {m.program.slug: m for m in page.matches}
    assert by_slug[program.slug].open_application_id == draft.pk
    assert by_slug[other.slug].open_application_id is None


def test_match_page_query_budget(term, django_assert_max_num_queries):
    school = SchoolFactory.create()
    for _ in range(2):
        program = ProgramFactory.create()
        program.allowed_schools.add(school)
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(
        profile=profile, school=school, gwa=88, gwa_scale="percent", units=18
    )
    with django_assert_max_num_queries(10):
        match_page(user_of(profile), today=TODAY)


def test_eligibility_for_uses_application_term():
    program = ProgramFactory.create()
    profile = FullProfileFactory.create()
    assert not eligibility_for(profile, program, today=TODAY).eligible
    AcademicTermFactory.create(school_year_start=2026, is_current=True)
    EducationRecordFactory.create(profile=profile)
    assert eligibility_for(profile, program, today=TODAY).eligible
