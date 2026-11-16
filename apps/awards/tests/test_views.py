import html
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.urls import reverse

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.models import Award
from apps.awards.tests.factories import RenewalFactory
from apps.awards.tests.scholars import add_record, make_scholar
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import AcademicTermFactory, BenefitTierFactory, ProgramFactory
from apps.students.models import StudentProfile
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db

PAGE = "scholarships:list"


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


def terms(current_number: int = 1) -> tuple[AcademicTerm, AcademicTerm]:
    previous = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(
        school_year_start=2026, term=current_number, is_current=True
    )
    return previous, current


def program_with_tier(previous: AcademicTerm, **fields: object) -> tuple[Program, BenefitTier]:
    fields.setdefault("name", "Alpha Grant")
    program = ProgramFactory.create(**fields)
    tier = BenefitTierFactory.create(
        program=program, effective_from=previous, code="standard", name="Standard"
    )
    return program, tier


def student() -> StudentProfile:
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(profile=profile)
    return profile


def user_of(award: Award) -> User:
    assert award.profile.user is not None
    return award.profile.user


def page(client, award: Award) -> str:
    client.force_login(user_of(award))
    response = client.get(reverse(PAGE))
    assert response.status_code == 200
    return html.unescape(response.content.decode())


@pytest.fixture
def due() -> tuple[Award, AcademicTerm]:
    previous, current = terms()
    program, tier = program_with_tier(previous)
    return make_scholar(program, tier, [previous], profile=student()), current


def test_page_lists_awards_with_terms(client, due) -> None:
    award, _ = due
    body = page(client, award)
    assert "Alpha Grant" in body
    assert "Standard" in body
    assert str(award.started_term) in body
    assert "88.00" in body


def test_renew_button_when_due(client, due) -> None:
    award, current = due
    body = page(client, award)
    assert f"Renew for {current}" in body
    assert reverse("scholarships:renew", args=[award.pk]) in body


def test_continue_link_when_open(client, due) -> None:
    award, current = due
    renewal = RenewalFactory.create(award=award, term=current)
    body = page(client, award)
    assert "Continue your renewal" in body
    assert reverse("applications:detail", args=[renewal.pk]) in body
    assert f"Renew for {current}" not in body


def test_renewed_sentence(client, due) -> None:
    award, current = due
    add_record(award, current)
    assert f"Renewed for {current}." in page(client, award)


def test_first_term_covers_sentence(client) -> None:
    previous, current = terms()
    program, tier = program_with_tier(previous)
    award = make_scholar(program, tier, [current], profile=student())
    body = page(client, award)
    assert f"Your scholarship covers {current}." in body
    assert "Renewed for" not in body


def test_summer_sentence(client) -> None:
    previous, _ = terms(3)
    program, tier = program_with_tier(previous)
    award = make_scholar(program, tier, [previous], profile=student())
    body = page(client, award)
    assert "Scholarships aren't renewed for the summer term." in body
    assert "Renew for" not in body


def test_window_sentence_when_closed(client) -> None:
    previous, _ = terms()
    program, tier = program_with_tier(previous, applications_close_on=date(2026, 10, 1))
    award = make_scholar(program, tier, [previous], profile=student())
    body = page(client, award)
    assert "Applications closed on 1 October 2026." in body
    assert reverse("scholarships:renew", args=[award.pk]) not in body


def test_on_hold_sentence(client, due) -> None:
    award, _ = due
    Award.objects.filter(pk=award.pk).update(status=Award.Status.SUSPENDED)
    assert "This scholarship is suspended." in page(client, award)


def test_renew_post_lands_on_application(client, due) -> None:
    award, _ = due
    client.force_login(user_of(award))
    response = client.post(reverse("scholarships:renew", args=[award.pk]))
    renewal = Application.objects.get(award=award)
    assert response.status_code == 302
    assert response.url == reverse("applications:detail", args=[renewal.pk])


def test_renew_post_refusal_message(client, due) -> None:
    award, current = due
    add_record(award, current)
    client.force_login(user_of(award))
    response = client.post(reverse("scholarships:renew", args=[award.pk]), follow=True)
    body = html.unescape(response.content.decode())
    assert f"Your scholarship is already renewed for {current}." in body
    assert not Application.objects.filter(award=award).exists()


def test_renew_other_students_award_404(client, due) -> None:
    award, _ = due
    client.force_login(student().user)
    assert client.post(reverse("scholarships:renew", args=[award.pk])).status_code == 404
    assert not Application.objects.exists()


def test_query_budget_two_awards_equals_one(client) -> None:
    previous, current = terms()
    program, tier = program_with_tier(previous)
    profile = student()
    award = make_scholar(program, tier, [previous], profile=profile)
    client.force_login(user_of(award))
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as one:
        client.get(reverse(PAGE))
    other, other_tier = program_with_tier(previous, slug="beta", name="Beta Grant")
    second = make_scholar(other, other_tier, [previous, current], profile=profile)
    RenewalFactory.create(award=award, term=current)
    with CaptureQueriesContext(connection) as two:
        body = html.unescape(client.get(reverse(PAGE)).content.decode())
    assert "Beta Grant" in body and second.pk
    assert len(two) == len(one)


def test_empty_state(client) -> None:
    client.force_login(student().user)
    body = client.get(reverse(PAGE)).content.decode()
    assert "No scholarships yet." in body


def test_nav_has_scholarships(client, due) -> None:
    award, _ = due
    body = page(client, award)
    assert f'href="{reverse(PAGE)}"' in body
    assert "Scholarships" in body
