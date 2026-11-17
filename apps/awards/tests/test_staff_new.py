import html
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.accounts.models import User
from apps.awards.models import Award
from apps.awards.services import already_holds
from apps.awards.tests.scholars import make_scholar
from apps.core.params import positive_id
from apps.programs.models import BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import FullProfileFactory, ProfileFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


class World:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program: Program = ProgramFactory.create()
        self.tier: BenefitTier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard", name="Standard"
        )
        self.staff: User = MembershipFactory.create(program=self.program).user
        self.walk_in: StudentProfile = FullProfileFactory.create(
            user=None,
            first_name="Felipe",
            last_name="Santos",
            created_for=self.program,
            created_by=self.staff,
        )

    def url(self, **params: Any) -> str:
        base = reverse("scholars:new", kwargs={"program": self.program.slug})
        if not params:
            return base
        from urllib.parse import urlencode

        return f"{base}?{urlencode(params)}"

    def post_data(self, **overrides: str) -> dict[str, str]:
        data = {
            "profile": str(self.walk_in.pk),
            "term": str(self.current.pk),
            "tier": "standard",
            "student_number": "2026-001",
            "notes": "",
            "school": "",
            "school_name": "Walk-in College",
            "school_type": "private",
            "gwa_scale": "percent",
            "course": "BSED",
            "year_level": "1",
            "gwa": "88.50",
            "units": "21",
        }
        data.update(overrides)
        return data


@pytest.fixture
def world(client) -> World:
    world = World()
    client.force_login(world.staff)
    return world


def test_positive_id():
    assert positive_id("12") == 12
    assert positive_id("0") is None
    assert positive_id("-3") is None
    assert positive_id("abc") is None
    assert positive_id("１２") is None  # not ASCII
    assert positive_id(str(2**31)) is None


def test_picker_lists_program_profiles(client, world: World, django_assert_max_num_queries):
    holder = make_scholar(
        world.program,
        world.tier,
        [world.previous],
        profile=FullProfileFactory.create(first_name="Ana", last_name="Cruz"),
    )
    stranger = ProfileFactory.create(first_name="Zed", last_name="Outsider")
    with django_assert_max_num_queries(12):
        response = client.get(world.url())
    assert response.status_code == 200
    page = html.unescape(response.content.decode())
    assert "Felipe Santos" in page
    assert "Ana Cruz" in page
    assert "Holds an award" in page
    assert world.url(profile=world.walk_in.pk).replace("&", "&amp;") in response.content.decode()
    assert f"profile={holder.profile.pk}" not in page
    assert stranger.last_name not in page


def test_picker_search(client, world: World):
    FullProfileFactory.create(
        user=None, first_name="Ana", last_name="Reyes", created_for=world.program
    )
    page = client.get(world.url(q="felipe")).content.decode()
    assert "Felipe Santos" in page
    assert "Ana Reyes" not in page


def test_picker_empty_state(client):
    program = ProgramFactory.create()
    AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    staff = MembershipFactory.create(program=program).user
    client.force_login(staff)
    page = client.get(reverse("scholars:new", kwargs={"program": program.slug})).content.decode()
    assert "No students yet." in page
    assert "Add a student first" in page
    assert reverse("workspace:students-new", kwargs={"program": program.slug}) in page


def test_form_for_profile(client, world: World):
    response = client.get(world.url(profile=world.walk_in.pk))
    assert response.status_code == 200
    form = response.context["form"]
    assert form.initial["term"] == world.current
    assert [code for code, _ in form.fields["tier"].choices] == ["standard"]
    assert list(form.fields["term"].queryset) == [world.current, world.previous]
    page = html.unescape(response.content.decode())
    assert "Felipe Santos" in page
    assert "Documents checked" in page


def test_foreign_profile_404(client, world: World):
    stranger = ProfileFactory.create()
    assert client.get(world.url(profile=stranger.pk)).status_code == 404
    response = client.post(world.url(), world.post_data(profile=str(stranger.pk)))
    assert response.status_code == 404
    assert not Award.objects.exists()


def test_bad_profile_param_shows_picker(client, world: World):
    response = client.get(world.url(profile="abc"))
    assert response.status_code == 200
    assert "form" not in response.context or response.context["form"] is None


def test_post_creates_and_redirects(client, world: World):
    response = client.post(world.url(), world.post_data())
    award = Award.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "scholars:detail", kwargs={"program": world.program.slug, "pk": award.pk}
    )
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Added Felipe Santos as a scholar."
    ]
    assert (award.source, award.student_number, award.tier) == ("manual", "2026-001", world.tier)
    assert award.terms.get().gwa == Decimal("88.50")


def test_post_holder_rerenders_400(client, world: World):
    make_scholar(world.program, world.tier, [world.previous], profile=world.walk_in)
    response = client.post(world.url(), world.post_data())
    assert response.status_code == 400
    assert already_holds(world.program) in html.unescape(response.content.decode())
    assert Award.objects.count() == 1


def test_post_missing_school_400(client, world: World):
    response = client.post(world.url(), world.post_data(school_name="", school_type=""))
    assert response.status_code == 400
    assert "Choose the student&#x27;s school or type its name." in response.content.decode()
    assert not Award.objects.exists()


def test_post_without_profile_400(client, world: World):
    response = client.post(world.url(), world.post_data(profile=""))
    assert response.status_code == 400
    assert "Choose a student first." in response.content.decode()


def test_inactive_program_404(client, world: World):
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    assert client.post(world.url(), world.post_data()).status_code == 404


def test_list_has_add_button(client, world: World):
    page = client.get(reverse("scholars:list", kwargs={"program": world.program.slug}))
    content = page.content.decode()
    assert world.url() in content
    assert "Add scholar" in content
