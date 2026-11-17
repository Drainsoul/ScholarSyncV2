"""Notification centres for staff and the office (M11c)."""

from datetime import timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.models import Notification
from apps.workspace.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def _staff(client: Any) -> tuple[User, Program]:
    program = ProgramFactory.create(slug="tcu-ceaa")
    user = MembershipFactory.create(program=program).user
    client.force_login(user)
    return user, program


def _office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _staff_url(program: Program, name: str = "list", pk: int | None = None) -> str:
    kwargs: dict[str, object] = {"program": program.slug}
    if pk is not None:
        kwargs["pk"] = pk
    return reverse(f"notifications-staff:{name}", kwargs=kwargs)


def _newest_first(user: User) -> None:
    now = timezone.now()
    for n in range(3):
        row = NotificationFactory.create(recipient=user, title=f"Mine {n:02d}", url="/office/")
        Notification.objects.filter(pk=row.pk).update(created_at=now - timedelta(minutes=n))
    NotificationFactory.create(title="Someone else's")


def test_staff_centre_lists_own_notifications_newest_first(client: Any) -> None:
    user, program = _staff(client)
    _newest_first(user)
    response = client.get(_staff_url(program))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Someone else" not in html
    assert html.index("Mine 00") < html.index("Mine 01") < html.index("Mine 02")
    assert 'class="switcher"' in html  # staff layout, with the program switcher


def test_office_centre_lists_own_notifications(client: Any) -> None:
    user = _office(client)
    _newest_first(user)
    response = client.get(reverse("office:notifications"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Someone else" not in html
    assert html.index("Mine 00") < html.index("Mine 01")
    assert "Scholarship office" in html  # office layout


def test_open_marks_read_and_follows_site_url(client: Any) -> None:
    user, program = _staff(client)
    row = NotificationFactory.create(recipient=user, url="/staff/tcu-ceaa/reports/")
    response = client.get(_staff_url(program, "open", row.pk))
    assert response.status_code == 302
    assert response["Location"] == "/staff/tcu-ceaa/reports/"
    row.refresh_from_db()
    assert row.read_at is not None

    office = _office(client)
    item = NotificationFactory.create(recipient=office, url="/office/reports/")
    response = client.get(reverse("office:notification-open", args=[item.pk]))
    assert response["Location"] == "/office/reports/"
    item.refresh_from_db()
    assert item.read_at is not None


def test_open_offsite_url_goes_to_centre(client: Any) -> None:
    user, program = _staff(client)
    row = NotificationFactory.create(recipient=user, url="https://evil.example/")
    response = client.get(_staff_url(program, "open", row.pk))
    assert response["Location"] == _staff_url(program)

    office = _office(client)
    item = NotificationFactory.create(recipient=office, url="//evil.example/")
    response = client.get(reverse("office:notification-open", args=[item.pk]))
    assert response["Location"] == reverse("office:notifications")


def test_other_users_notification_404_stays_unread(client: Any) -> None:
    _user, program = _staff(client)
    theirs = NotificationFactory.create()
    assert client.get(_staff_url(program, "open", theirs.pk)).status_code == 404
    _office(client)
    assert client.get(reverse("office:notification-open", args=[theirs.pk])).status_code == 404
    theirs.refresh_from_db()
    assert theirs.read_at is None


def test_staff_without_membership_403(client: Any) -> None:
    user, _program = _staff(client)
    lani = ProgramFactory.create(slug="lani")
    row = NotificationFactory.create(recipient=user)
    assert client.get(_staff_url(lani, "open", row.pk)).status_code == 403
    row.refresh_from_db()
    assert row.read_at is None


def test_mark_all_read_staff_and_office(client: Any) -> None:
    user, program = _staff(client)
    NotificationFactory.create_batch(2, recipient=user)
    response = client.post(_staff_url(program, "read-all"))
    assert response["Location"] == _staff_url(program)
    assert not Notification.objects.filter(recipient=user, read_at=None).exists()

    office = _office(client)
    NotificationFactory.create_batch(2, recipient=office)
    response = client.post(reverse("office:notifications-read"))
    assert response["Location"] == reverse("office:notifications")
    assert not Notification.objects.filter(recipient=office, read_at=None).exists()


def test_bell_on_staff_and_office_pages_with_unread_label(client: Any) -> None:
    user, program = _staff(client)
    NotificationFactory.create_batch(2, recipient=user)
    html = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug})).content
    assert b'aria-label="Notifications, 2 unread"' in html
    assert _staff_url(program).encode() in html

    office = _office(client)
    NotificationFactory.create(recipient=office)
    html = client.get(reverse("office:home")).content
    assert b'aria-label="Notifications, 1 unread"' in html
    assert reverse("office:notifications").encode() in html
