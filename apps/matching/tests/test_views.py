import html
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.tests.factories import AwardFactory
from apps.programs.models import School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    SchoolFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db

URL = "/me/match/"
BUDGET = 12  # measured 10


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


@pytest.fixture
def term():
    return AcademicTermFactory.create(school_year_start=2026, is_current=True)


def get(client, user):
    client.force_login(user)
    return client.get(reverse("matching:match"))


def text(response) -> str:
    return html.unescape(response.content.decode())


def test_url_is_under_me_match():
    assert reverse("matching:match") == URL


def test_no_profile_shows_empty_state_and_creates_nothing(client, term):
    response = get(client, UserFactory.create(verified=True))
    body = text(response)
    assert "Start your profile first" in body
    assert reverse("students:profile") in body
    assert StudentProfile.objects.count() == 0


def test_eligible_program_shows_apply_link(client, term):
    program = ProgramFactory.create(name="Alpha")
    BenefitTierFactory.create(program=program, effective_from=term, name="Standard")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    body = text(get(client, profile.user))
    assert "Find scholarships" in body
    assert "You qualify" in body
    assert "Allowance tiers: Standard" in body
    assert f'href="/me/applications/new/{program.slug}/"' in body
    assert ">Apply<" in body


def test_missing_school_shows_fix_link(client, term):
    ProgramFactory.create(name="Alpha")
    profile = FullProfileFactory.create()
    body = text(get(client, profile.user))
    assert "Not yet" in body
    assert "is-missing" in body
    assert "Fix this in your profile" in body
    assert reverse("students:profile-education") in body
    assert "Apply<" not in body


def test_hint_shown_for_percent_student_with_income(client, term):
    profile = FullProfileFactory.create(monthly_household_income=Decimal("15000.00"))
    EducationRecordFactory.create(profile=profile, gwa=Decimal("90.00"), gwa_scale="percent")
    body = text(get(client, profile.user))
    assert "v1's model suggests" in body
    assert "%)." in body
    assert "Advisory only: the program rules above decide." in body


def test_hint_reason_for_one_to_five_student(client, term):
    school = SchoolFactory.create(grading_scale=School.Scale.ONE_TO_FIVE)
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(
        profile=profile, school=school, gwa=Decimal("1.50"), gwa_scale="one_to_five"
    )
    body = text(get(client, profile.user))
    assert "The legacy model only reads percent grades." in body
    assert "v1's model suggests" not in body


def test_no_term_sentence(client):
    profile = FullProfileFactory.create()
    body = text(get(client, profile.user))
    assert "No school term is set up yet." in body


def test_term_line(client, term):
    profile = FullProfileFactory.create()
    body = text(get(client, profile.user))
    assert f"For {term}" in body


def test_continue_link_for_open_application(client, term):
    program = ProgramFactory.create(name="Alpha")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    application = ApplicationFactory.create(
        profile=profile, program=program, term=term, status=Application.Status.SUBMITTED
    )
    body = text(get(client, profile.user))
    assert "Continue your application" in body
    assert f'href="/me/applications/{application.pk}/"' in body
    assert ">Apply<" not in body


def test_nav_has_find_scholarships_and_applications(client, term):
    profile = FullProfileFactory.create()
    body = text(get(client, profile.user))
    assert 'href="/me/applications/"' in body


def test_checklist_announces_each_state(client, term):
    ProgramFactory.create(name="Alpha")
    profile = FullProfileFactory.create()
    body = text(get(client, profile.user))
    assert '<span class="visually-hidden">Met: </span>' in body
    assert '<span class="visually-hidden">Missing: </span>' in body


def test_match_page_view_query_budget(client, term, django_assert_max_num_queries):
    school = SchoolFactory.create()
    first = ProgramFactory.create(name="Alpha")
    second = ProgramFactory.create(name="Bravo")
    first.allowed_schools.add(school)
    BenefitTierFactory.create(program=second, effective_from=term)
    profile = FullProfileFactory.create(monthly_household_income=Decimal("15000.00"))
    EducationRecordFactory.create(
        profile=profile, school=school, gwa=Decimal("90.00"), gwa_scale="percent", units=18
    )
    ApplicationFactory.create(profile=profile, program=first, term=term)
    client.force_login(profile.user)
    with django_assert_max_num_queries(BUDGET):
        assert client.get(reverse("matching:match")).status_code == 200


def _held_world(term):
    program = ProgramFactory.create(name="Alpha")
    BenefitTierFactory.create(program=program, effective_from=term, name="Standard")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    return program, profile


def test_match_page_shows_held_instead_of_apply(client, term, django_assert_max_num_queries):
    program, profile = _held_world(term)
    other = ProgramFactory.create(name="Bravo")
    get(client, profile.user)
    with CaptureQueriesContext(connection) as before:
        body = text(client.get(reverse("matching:match")))
    assert "You already hold this scholarship." not in body
    AwardFactory.create(
        profile=profile,
        program=program,
        source_application=ApplicationFactory.create(
            profile=profile, program=program, term=term, status=Application.Status.APPROVED
        ),
    )
    ApplicationFactory.create(
        profile=profile, program=other, term=term, status=Application.Status.APPROVED
    )
    with CaptureQueriesContext(connection) as after:
        response = client.get(reverse("matching:match"))
    body = text(response)
    assert body.count("You already hold this scholarship.") == 2
    assert reverse("applications:new", args=[program.slug]) not in body
    assert ">Apply<" not in body
    assert len(after) <= len(before) + 1
    assert Application.objects.count() == 2


REJECTED = "This application wasn't approved for {}. You can apply again next term."


def test_match_page_shows_rejected_instead_of_apply(client, term, django_assert_max_num_queries):
    program, profile = _held_world(term)
    get(client, profile.user)
    with CaptureQueriesContext(connection) as before:
        body = text(client.get(reverse("matching:match")))
    assert REJECTED.format(term) not in body
    assert reverse("applications:new", args=[program.slug]) in body
    ApplicationFactory.create(
        profile=profile, program=program, term=term, status=Application.Status.REJECTED
    )
    with CaptureQueriesContext(connection) as after:
        body = text(client.get(reverse("matching:match")))
    assert REJECTED.format(term) in body
    assert reverse("applications:new", args=[program.slug]) not in body
    assert len(after) <= len(before)


def test_match_page_open_application_wins_over_rejected(client, term):
    program, profile = _held_world(term)
    ApplicationFactory.create(
        profile=profile, program=program, term=term, status=Application.Status.REJECTED
    )
    open_one = ApplicationFactory.create(profile=profile, program=program, term=term)
    body = text(get(client, profile.user))
    assert reverse("applications:detail", args=[open_one.pk]) in body
    assert REJECTED.format(term) not in body


def test_view_link_for_on_behalf_open_application(client, term):
    program = ProgramFactory.create(name="Alpha")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    ApplicationFactory.create(
        profile=profile, program=program, term=term, on_behalf=True, status=Application.Status.DRAFT
    )
    body = text(get(client, profile.user))
    assert "View your application" in body
    assert "Continue your application" not in body


def test_match_page_marks_suspended_as_held(client, term):
    program, profile = _held_world(term)
    AwardFactory.create(
        profile=profile,
        program=program,
        status="suspended",
        source_application=ApplicationFactory.create(
            profile=profile, program=program, term=term, status=Application.Status.APPROVED
        ),
    )
    Application.objects.filter(profile=profile).update(term=AcademicTermFactory.create())
    body = text(get(client, profile.user))
    assert "You already hold this scholarship." in body
    assert reverse("applications:new", args=[program.slug]) not in body
