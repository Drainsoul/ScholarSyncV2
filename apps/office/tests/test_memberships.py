from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.core.shell import home_url_for
from apps.core.tests.auth import reauthenticated, replay_after_password, signed_in_long_ago
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db

HEAD = ProgramMembership.Level.HEAD
STAFF = ProgramMembership.Level.STAFF


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    reauthenticated(client, user)
    return user


def _staff() -> User:
    return UserFactory.create(role=User.Role.STAFF, verified=True, full_name="Ana Reyes")


def _add(client: Any, user: User, program: Program, level: str = STAFF) -> Any:
    url = reverse("office:membership-add", args=[user.pk])
    return client.post(url, {"program": str(program.pk), "level": level}, follow=True)


def test_add_change_remove_round_trip(client: Any, office: User) -> None:
    user, program = _staff(), ProgramFactory.create(name="LANI")
    assert "Added to LANI." in _add(client, user, program).content.decode()
    membership = ProgramMembership.objects.get(user=user, program=program)
    change = reverse("office:membership-change", args=[membership.pk])
    response = client.post(change, {"level": HEAD}, follow=True)
    assert "Now Program head in LANI." in response.content.decode()
    client.post(change, {"level": HEAD})  # no change, no event
    response = client.post(change, {"remove": "1"}, follow=True)
    assert "Removed from LANI." in response.content.decode()
    assert not ProgramMembership.objects.exists()
    events = AuditEvent.objects.exclude(action="user.signed_in").order_by("pk")
    assert [event.action for event in events] == [
        "membership.added",
        "membership.changed",
        "membership.removed",
    ]
    assert events[1].data == {"from": "staff", "to": "head"}
    assert all(event.program == program for event in events)


def test_duplicate_membership_is_a_form_error(client: Any, office: User) -> None:
    user, program = _staff(), ProgramFactory.create(name="LANI")
    MembershipFactory.create(user=user, program=program)
    html = _add(client, user, program).content.decode()
    assert "Ana Reyes is already in LANI." in html
    assert ProgramMembership.objects.count() == 1


def test_office_account_cannot_be_a_member(client: Any, office: User) -> None:
    other = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    html = _add(client, other, ProgramFactory.create()).content.decode()
    assert "Only program staff accounts can be program members." in html
    assert not ProgramMembership.objects.exists()


def test_membership_of_unknown_pk_404(client: Any, office: User) -> None:
    url = reverse("office:membership-change", args=[999999])
    assert client.post(url, {"remove": "1"}).status_code == 404


def test_add_membership_replays_after_password(client: Any) -> None:
    """A stale login goes to the password page, and the replayed POST adds
    exactly one membership and lands on the account page."""
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    user, program = _staff(), ProgramFactory.create()
    signed_in_long_ago(client, office)
    url = reverse("office:membership-add", args=[user.pk])
    response = client.post(url, {"program": str(program.pk), "level": STAFF})
    assert not ProgramMembership.objects.exists()
    replayed = replay_after_password(client, response)
    assert replayed.status_code == 302
    assert replayed.url == reverse("office:staff-detail", args=[user.pk])
    assert ProgramMembership.objects.filter(user=user, program=program).count() == 1


def test_change_needs_reauthentication(client: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    membership = MembershipFactory.create()
    signed_in_long_ago(client, office)
    url = reverse("office:membership-change", args=[membership.pk])
    response = client.post(url, {"remove": "1"})
    assert response.url.startswith(reverse("account_reauthenticate"))
    assert ProgramMembership.objects.filter(pk=membership.pk).exists()


def test_new_member_lands_on_the_program(client: Any, office: User) -> None:
    user, program = _staff(), ProgramFactory.create()
    assert home_url_for(user) == reverse("workspace:no_programs")
    _add(client, user, program)
    assert home_url_for(user) == reverse("workspace:dashboard", kwargs={"program": program.slug})


def test_detail_page_shows_membership_forms(client: Any, office: User) -> None:
    user = _staff()
    MembershipFactory.create(user=user, program=ProgramFactory.create(name="LANI"))
    html = client.get(reverse("office:staff-detail", args=[user.pk])).content.decode()
    assert "Add to a program" in html
    assert "LANI" in html and "Remove" in html
