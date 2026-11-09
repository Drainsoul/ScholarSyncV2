import html
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db

URL = "/me/match/"


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
    from apps.programs.models import School
    from apps.programs.tests.factories import SchoolFactory

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
