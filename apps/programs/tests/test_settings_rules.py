from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.core.text import normalize_newlines
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db


def _head(program: Program) -> User:
    return MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user


def _url(program: Program) -> str:
    return reverse("settings:rules", kwargs={"program": program.slug})


def _data(**changes: object) -> dict[str, object]:
    """The rules form as the page posts it, every field blank or unticked."""
    data: dict[str, object] = {
        "applications_open_on": "",
        "applications_close_on": "",
        "min_gwa_percent": "",
        "max_gwa_one_to_five": "",
        "min_units": "",
        "min_residency_years": "",
        "renewal_min_gwa_percent": "",
        "renewal_max_gwa_one_to_five": "",
        "renewal_min_units": "",
        "merit_min_gwa_percent": "",
        "merit_max_gwa_one_to_five": "",
        "max_terms": "",
        "claim_location_default": "",
    }
    data.update(changes)
    return data


def test_head_saves_rules_and_one_event_lists_changed_fields(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(_head(program))
    response = client.post(
        _url(program),
        _data(min_gwa_percent="85", renewal_min_units="15", requires_registered_voter="on"),
        follow=True,
    )
    assert "Rules saved." in response.content.decode()
    program.refresh_from_db()
    assert program.min_gwa_percent == Decimal("85")
    assert program.renewal_min_units == 15
    assert program.requires_registered_voter is True
    event = AuditEvent.objects.get(action="program.rules_changed")
    assert sorted(event.data["fields"]) == [
        "min_gwa_percent",
        "renewal_min_units",
        "requires_registered_voter",
    ]


def test_staff_403_other_head_403(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(MembershipFactory.create(program=program).user)
    assert client.get(_url(program)).status_code == 403
    client.force_login(_head(ProgramFactory.create()))
    assert client.get(_url(program)).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"min_gwa_percent": "101"},
        {"max_gwa_one_to_five": "0.99"},
        {"renewal_max_gwa_one_to_five": "5.01"},
        {"min_units": "41"},
        {"min_residency_years": "51"},
        {"applications_open_on": "2026-12-01", "applications_close_on": "2026-11-01"},
    ],
)
def test_out_of_range_values_rejected(client: Any, changes: dict[str, str]) -> None:
    program = ProgramFactory.create()
    client.force_login(_head(program))
    response = client.post(_url(program), _data(**changes))
    assert response.status_code == 200
    assert not AuditEvent.objects.exclude(action="user.signed_in").exists()


def test_saving_unchanged_writes_no_event(client: Any) -> None:
    program = ProgramFactory.create(min_gwa_percent=Decimal("80"))
    client.force_login(_head(program))
    client.post(_url(program), _data(min_gwa_percent="80.00"))
    assert not AuditEvent.objects.exclude(action="user.signed_in").exists()


def test_window_and_new_rules_reach_the_public_page(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(_head(program))
    client.post(
        _url(program),
        _data(min_gwa_percent="85", applications_close_on=date(2026, 12, 15).isoformat()),
    )
    program.refresh_from_db()
    assert program.applications_close_on == date(2026, 12, 15)
    page = client.get(reverse("programs:detail", kwargs={"slug": program.slug})).content.decode()
    assert "A GWA of at least 85% (schools that grade in percent)." in page


def test_settings_nav_only_for_heads_and_office(client: Any) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa")
    dashboard = reverse("workspace:dashboard", kwargs={"program": program.slug})

    def secondary(user: User) -> list[str]:
        client.force_login(user)
        items = client.get(dashboard).context.get("nav_secondary") or []
        return [item["label"] for item in items]

    assert secondary(_head(program)) == ["Settings", "Audit log"]
    assert secondary(UserFactory.create(role=User.Role.SUPER_ADMIN)) == ["Settings", "Audit log"]
    assert secondary(MembershipFactory.create(program=program).user) == []


def test_office_saves_rules_of_a_closed_program(client: Any) -> None:
    program = ProgramFactory.create(is_active=False)
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
    page = client.get(_url(program)).content.decode()
    assert f"{program.name} is closed." in page
    client.post(_url(program), _data(min_units="12"))
    program.refresh_from_db()
    assert program.min_units == 12


def test_normalize_newlines() -> None:
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_rules_save_ignores_school_type_order(client: Any) -> None:
    from apps.programs import services

    program = ProgramFactory.create(allowed_school_types=["public", "private"])
    changed = services.update_rules(
        actor=_head(program), program=program, data={"allowed_school_types": ["private", "public"]}
    )
    assert changed == []
    assert not AuditEvent.objects.filter(action="program.rules_changed").exists()


def test_settings_links_work_for_a_closed_program(client: Any) -> None:
    import re

    program = ProgramFactory.create(is_active=False)
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
    page = client.get(_url(program)).content.decode()
    nav = page[page.index('<nav class="sidebar') : page.index("</nav>")]
    links = set(re.findall(r'href="(/staff/[^"]+)"', nav))
    assert _url(program) in links  # Settings stays
    for link in links:
        assert client.get(link).status_code == 200, link
