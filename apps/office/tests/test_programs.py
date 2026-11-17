from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.core.models import AuditEvent
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)

pytestmark = pytest.mark.django_db

LIST = "/office/programs/"
NEED_SETUP = "Add an allowance tier and a required document before opening {name}."


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    client.force_login(user)
    return user


def _ready(program: Program) -> None:
    """A tier in force for the current term and a required document."""
    term = AcademicTermFactory.create(is_current=True)
    BenefitTierFactory.create(program=program, effective_from=term)
    RequiredDocumentFactory.create(program=program)


def _active(client: Any, program: Program, active: bool) -> Any:
    url = reverse("office:program-active", args=[program.pk])
    return client.post(url, {"active": "1" if active else "0"}, follow=True)


def test_list_shows_active_and_inactive_with_status_and_links(client: Any, office: User) -> None:
    open_one = ProgramFactory.create(name="Open Grant")
    closed = ProgramFactory.create(name="Closed Grant", is_active=False)
    html = client.get(LIST).content.decode()
    assert "Open Grant" in html and "Closed Grant" in html
    assert reverse("office:program-edit", args=[closed.pk]) in html
    assert reverse("workspace:dashboard", kwargs={"program": open_one.slug}) in html
    assert f'href="{reverse("workspace:dashboard", kwargs={"program": closed.slug})}"' not in html
    assert reverse("settings:rules", kwargs={"program": closed.slug}) in html
    inactive_tab = client.get(LIST + "?tab=inactive").content.decode()
    assert "Closed Grant" in inactive_tab and "Open Grant" not in inactive_tab


def test_create_starts_inactive_and_audits(client: Any, office: User) -> None:
    response = client.post(
        reverse("office:program-new"),
        {"slug": "arts-grant", "name": "Taguig Arts Grant", "description": "For artists."},
    )
    program = Program.objects.get(slug="arts-grant")
    assert response.status_code == 302
    assert response["Location"] == reverse("settings:rules", kwargs={"program": "arts-grant"})
    assert not program.is_active
    event = AuditEvent.objects.get(action="program.created")
    assert event.program == program
    assert "Arts" not in str(event.data)


def test_slug_taken_and_slug_is_fixed_on_edit(client: Any, office: User) -> None:
    program = ProgramFactory.create(slug="lani", name="LANI")
    response = client.post(reverse("office:program-new"), {"slug": "LANI", "name": "Another"})
    assert "That slug is taken." in response.content.decode()
    edit = reverse("office:program-edit", args=[program.pk])
    client.post(edit, {"slug": "changed", "name": "LANI Plus", "description": ""})
    program.refresh_from_db()
    assert (program.slug, program.name) == ("lani", "LANI Plus")
    assert AuditEvent.objects.filter(action="program.updated").count() == 1


def test_activate_needs_a_tier_and_a_document(client: Any, office: User) -> None:
    program = ProgramFactory.create(name="Arts Grant", is_active=False)
    response = _active(client, program, True)
    assert NEED_SETUP.format(name="Arts Grant") in response.content.decode()
    program.refresh_from_db()
    assert not program.is_active
    assert not AuditEvent.objects.exists()


def test_activate_then_deactivate(client: Any, office: User) -> None:
    program = ProgramFactory.create(is_active=False)
    _ready(program)
    _active(client, program, True)
    program.refresh_from_db()
    assert program.is_active
    _active(client, program, True)  # no change, no second event
    _active(client, program, False)
    assert not Program.objects.get(pk=program.pk).is_active
    actions = list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))
    assert actions == ["program.activated", "program.deactivated"]


def test_deactivate_refused_with_waiting_work(client: Any, office: User) -> None:
    program = ProgramFactory.create(name="Busy Grant")
    ApplicationFactory.create(program=program, status=Application.Status.SUBMITTED)
    ApplicationFactory.create(program=program, status=Application.Status.UNDER_REVIEW)
    schedule = ScheduleFactory.create(program=program)
    payout(schedule)
    payout(schedule, status=Disbursement.Status.RELEASED)
    html = _active(client, program, False).content.decode()
    assert (
        "Busy Grant still has 2 waiting applications and 1 payout in progress. "
        "Finish or reject them first."
    ) in html.replace("&#x27;", "'")
    program.refresh_from_db()
    assert program.is_active


def test_office_reaches_settings_of_inactive_program_staff_do_not(client: Any) -> None:
    program = ProgramFactory.create(is_active=False)
    head = MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    settings_url = reverse("settings:rules", kwargs={"program": program.slug})
    dashboard = reverse("workspace:dashboard", kwargs={"program": program.slug})
    client.force_login(office)
    assert client.get(settings_url).status_code == 200
    assert client.get(dashboard).status_code == 404
    client.force_login(head)
    assert client.get(settings_url).status_code == 404
    assert client.get(dashboard).status_code == 404


def test_office_nav_order(client: Any, office: User) -> None:
    response = client.get(LIST)
    labels = [item["label"] for item in response.context["nav_items"]]
    assert labels[:2] == ["Overview", "Programs"]
    assert labels[-2:] == ["Terms", "Support"]
    programs = next(item for item in response.context["nav_items"] if item["label"] == "Programs")
    assert programs["current"] is True


def test_programs_list_query_count(
    client: Any, office: User, django_assert_max_num_queries: Any
) -> None:
    ProgramFactory.create_batch(50)
    with django_assert_max_num_queries(10):
        assert client.get(LIST).status_code == 200


def test_deactivate_refused_with_returned_applications(client: Any, office: User) -> None:
    """A returned application could be resubmitted into a closed program where
    nobody sees it, so returned ones keep the program open too."""
    program = ProgramFactory.create(name="Quiet Grant")
    ApplicationFactory.create(program=program, status=Application.Status.RETURNED)
    html = _active(client, program, False).content.decode().replace("&#x27;", "'")
    assert (
        "Quiet Grant still has 1 waiting application and 0 payouts in progress. "
        "Finish or reject them first."
    ) in html
    program.refresh_from_db()
    assert program.is_active
