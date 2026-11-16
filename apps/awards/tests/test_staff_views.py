import html
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.awards.models import Award
from apps.awards.tests.scholars import make_scholar
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.tests.factories import FullProfileFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


class World:
    def __init__(self, **program_fields: object) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        values: dict[str, object] = {"renewal_min_gwa_percent": Decimal("80")}
        values.update(program_fields)
        self.program: Program = ProgramFactory.create(**values)
        self.tier: BenefitTier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard", name="Standard"
        )
        self.staff: User = MembershipFactory.create(program=self.program).user

    def scholar(
        self,
        first: str = "Ana",
        last: str = "Cruz",
        *,
        terms: list[AcademicTerm] | None = None,
        **fields: Any,
    ) -> Award:
        profile = FullProfileFactory.create(first_name=first, last_name=last)
        return make_scholar(
            self.program,
            fields.pop("tier", self.tier),
            terms or [self.previous],
            profile=profile,
            **fields,
        )

    def url(self, **params: str) -> str:
        base = reverse("scholars:list", kwargs={"program": self.program.slug})
        if not params:
            return base
        from urllib.parse import urlencode

        return f"{base}?{urlencode(params)}"


@pytest.fixture
def world() -> World:
    return World()


def body(client, user: User, url: str) -> str:
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200
    return html.unescape(response.content.decode())


def test_default_tab_active(client, world: World) -> None:
    world.scholar("Ana", "Active")
    world.scholar("Sol", "Held", status=Award.Status.SUSPENDED)
    page = body(client, world.staff, world.url())
    assert "Ana Active" in page
    assert "Sol Held" not in page


@pytest.mark.parametrize(
    ("tab", "expected"),
    [
        ("active", {"Ana Active", "Rex Risk", "Dan Due"}),
        ("suspended", {"Sol Held"}),
        ("inactive", {"Ivy Ended"}),
        ("graduated", {"Gil Grad"}),
        ("at_risk", {"Rex Risk"}),
        ("not_renewed", {"Rex Risk", "Dan Due"}),
        ("all", {"Ana Active", "Rex Risk", "Dan Due", "Sol Held", "Ivy Ended", "Gil Grad"}),
    ],
)
def test_each_tab_filters(client, world: World, tab: str, expected: set[str]) -> None:
    world.scholar("Ana", "Active", terms=[world.previous, world.current])
    world.scholar("Rex", "Risk", gwa=Decimal("70"))
    world.scholar("Dan", "Due")
    world.scholar("Sol", "Held", status=Award.Status.SUSPENDED)
    world.scholar("Ivy", "Ended", status=Award.Status.INACTIVE)
    world.scholar("Gil", "Grad", status=Award.Status.GRADUATED)
    page = body(client, world.staff, world.url(status=tab))
    everyone = {"Ana Active", "Rex Risk", "Dan Due", "Sol Held", "Ivy Ended", "Gil Grad"}
    assert {name for name in everyone if name in page} == expected


def test_search_every_word(client, world: World) -> None:
    world.scholar("Maria", "Santos")
    world.scholar("Maria", "Reyes")
    page = body(client, world.staff, world.url(q="maria rey"))
    assert "Maria Reyes" in page
    assert "Maria Santos" not in page


def test_tier_filter_by_code(client, world: World) -> None:
    other = BenefitTierFactory.create(
        program=world.program, effective_from=world.previous, code="honors", name="Honors"
    )
    world.scholar("Ana", "Standard")
    world.scholar("Hal", "Honors", tier=other)
    page = body(client, world.staff, world.url(tier="honors"))
    assert "Hal Honors" in page
    assert "Ana Standard" not in page


def test_unknown_values_fall_back(client, world: World) -> None:
    world.scholar("Ana", "Active")
    page = body(client, world.staff, world.url(status="bogus", tier="nope", page="abc"))
    assert "Ana Active" in page


def test_pagination_25(client, world: World) -> None:
    for number in range(26):
        world.scholar("Pat", f"Person{number:02d}")
    first = body(client, world.staff, world.url())
    assert "Person24" in first and "Person25" not in first
    second = body(client, world.staff, world.url(page="2"))
    assert "Person25" in second


def test_drawer_shows_facts_and_reasons(client, world: World) -> None:
    world_closed = world
    award = world_closed.scholar("Rex", "Risk", gwa=Decimal("70"))
    page = body(client, world.staff, world.url(scholar=str(award.pk)))
    assert "Scholar details" in page
    assert "Factory College" in page
    assert "Standard" in page
    assert str(world.previous) in page
    assert "Last term's GWA of 70.00 misses the renewal mark." in page
    assert f"Due to renew for {world.current}." in page


def test_drawer_foreign_id_ignored(client, world: World) -> None:
    other = World.__new__(World)
    other.previous, other.current = world.previous, world.current
    other.program = ProgramFactory.create()
    other.tier = BenefitTierFactory.create(program=other.program, effective_from=world.previous)
    foreign = make_scholar(other.program, other.tier, [world.previous])
    page = body(client, world.staff, world.url(scholar=str(foreign.pk)))
    assert "Scholar details" not in page
    page = body(client, world.staff, world.url(scholar="not-a-number"))
    assert "Scholar details" not in page


def test_list_query_budget(client, world: World) -> None:
    for number in range(3):
        world.scholar("Few", f"Row{number}")
    client.force_login(world.staff)
    with CaptureQueriesContext(connection) as few:
        client.get(world.url())
    for number in range(22):
        world.scholar("Many", f"Row{number}")
    with CaptureQueriesContext(connection) as many:
        client.get(world.url())
    assert len(many) == len(few)
    assert len(few) <= 14


def test_other_program_staff_403(client, world: World) -> None:
    outsider = MembershipFactory.create(program=ProgramFactory.create()).user
    client.force_login(outsider)
    assert client.get(world.url()).status_code == 403


def test_nav_has_scholars(client, world: World) -> None:
    page = body(client, world.staff, world.url())
    assert f'href="{world.url()}"' in page
    assert ">Scholars<" in page or "Scholars</" in page


def test_window_closed_marks_not_renewed_at_risk(client) -> None:
    closed = World(applications_close_on=date(2026, 10, 1))
    closed.scholar("Dan", "Due")
    page = body(client, closed.staff, closed.url(status="at_risk"))
    assert "Dan Due" in page


# --- The scholar record ---


def record_url(world: World, award: Award, name: str = "scholars:detail") -> str:
    return reverse(name, kwargs={"program": world.program.slug, "pk": award.pk})


def test_record_shows_terms_newest_first(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz", terms=[world.previous, world.current])
    page = body(client, world.staff, record_url(world, award))
    assert "Ana Cruz" in page
    assert page.index(str(world.current)) < page.index(str(world.previous), page.index("Terms"))


def test_record_shows_only_allowed_actions(client, world: World) -> None:
    active = world.scholar("Ana", "Active")
    page = body(client, world.staff, record_url(world, active))
    assert "Put on hold" in page and "End award" in page and "Mark graduated" in page
    assert "Reinstate" not in page
    graduated = world.scholar("Gil", "Grad", status=Award.Status.GRADUATED)
    page = body(client, world.staff, record_url(world, graduated))
    for label in ("Put on hold", "End award", "Mark graduated", "Reinstate"):
        assert label not in page


def test_record_lists_source_application_and_renewals(client, world: World) -> None:
    from apps.awards.tests.factories import RenewalFactory

    award = world.scholar("Ana", "Cruz")
    renewal = RenewalFactory.create(
        award=award,
        term=world.current,
        status="submitted",
        submitted_at=timezone.now(),
        school_name="College",
    )
    page = body(client, world.staff, record_url(world, award))
    assert (
        reverse("review:detail", kwargs={"program": world.program.slug, "pk": renewal.pk}) in page
    )


def test_status_page_and_post(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz")
    url = record_url(world, award, "scholars:status")
    page = body(client, world.staff, f"{url}?to=suspended")
    assert "Put on hold" in page
    response = client.post(url, {"to": "suspended", "reason": "Missing enrolment."}, follow=True)
    page = html.unescape(response.content.decode())
    assert "Put on hold. The award is now suspended." in page
    award.refresh_from_db()
    assert award.status == Award.Status.SUSPENDED


def test_status_post_error_rerenders_400(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz")
    client.force_login(world.staff)
    response = client.post(
        record_url(world, award, "scholars:status"), {"to": "suspended", "reason": ""}
    )
    assert response.status_code == 400
    assert "Say why you're putting this award on hold." in html.unescape(response.content.decode())


def test_status_page_unknown_target_goes_back(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz")
    client.force_login(world.staff)
    response = client.get(record_url(world, award, "scholars:status") + "?to=bogus")
    assert response.status_code == 302
    assert response.url == record_url(world, award)


def test_edit_round_trip(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz")
    url = record_url(world, award, "scholars:edit")
    page = body(client, world.staff, url)
    assert "Student number" in page
    response = client.post(
        url, {"student_number": "2026-0007", "notes": "Call first.", "tier": world.tier.pk}
    )
    assert response.status_code == 302
    award.refresh_from_db()
    assert (award.student_number, award.notes) == ("2026-0007", "Call first.")


def test_record_query_budget(client, world: World, django_assert_max_num_queries) -> None:
    award = world.scholar("Ana", "Cruz", terms=[world.previous, world.current])
    client.force_login(world.staff)
    with django_assert_max_num_queries(16):
        assert client.get(record_url(world, award)).status_code == 200


def test_record_foreign_award_404(client, world: World) -> None:
    foreign = make_scholar(
        ProgramFactory.create(),
        BenefitTierFactory.create(effective_from=world.previous),
        [world.previous],
    )
    client.force_login(world.staff)
    for name in ("scholars:detail", "scholars:edit", "scholars:status"):
        assert client.get(record_url(world, foreign, name)).status_code == 404
    response = client.post(
        record_url(world, foreign, "scholars:status"), {"to": "suspended", "reason": "x"}
    )
    assert response.status_code == 404


def test_drawer_links_to_record(client, world: World) -> None:
    award = world.scholar("Ana", "Cruz")
    page = body(client, world.staff, world.url(scholar=str(award.pk)))
    assert record_url(world, award) in page
    assert "Open record" in page
