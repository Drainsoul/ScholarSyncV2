from datetime import timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.workspace.models import Notification
from apps.workspace.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db

CENTER = "/me/notifications/"


def _student(client: Any) -> Any:
    user = UserFactory.create()
    client.force_login(user)
    return user


def test_center_lists_own_notifications_newest_first_paginated(client: Any) -> None:
    user = _student(client)
    now = timezone.now()
    for n in range(30):
        row = NotificationFactory.create(recipient=user, title=f"Mine {n:02d}")
        Notification.objects.filter(pk=row.pk).update(created_at=now - timedelta(minutes=n))
    NotificationFactory.create(title="Someone else's")
    response = client.get(CENTER)
    assert response.status_code == 200
    html = response.content.decode()
    assert "Someone else" not in html
    assert html.index("Mine 00") < html.index("Mine 01")
    assert "Mine 24" in html and "Mine 25" not in html
    assert "Mine 25" in client.get(CENTER + "?page=2").content.decode()


def test_unread_rows_show_new(client: Any) -> None:
    user = _student(client)
    NotificationFactory.create(recipient=user, title="Unread one")
    NotificationFactory.create(recipient=user, title="Read one", read_at=timezone.now())
    html = client.get(CENTER).content.decode()
    assert html.count(">New<") == 1


def test_open_marks_read_and_redirects_to_its_url(client: Any) -> None:
    user = _student(client)
    row = NotificationFactory.create(recipient=user, url="/me/scholarships/")
    response = client.get(reverse("notifications:open", args=[row.pk]))
    assert response.status_code == 302
    assert response["Location"] == "/me/scholarships/"
    row.refresh_from_db()
    first = row.read_at
    assert first is not None
    client.get(reverse("notifications:open", args=[row.pk]))
    row.refresh_from_db()
    assert row.read_at == first


@pytest.mark.parametrize("url", ["https://evil.example/", "//evil.example", ""])
def test_open_offsite_or_blank_url_redirects_to_the_center(client: Any, url: str) -> None:
    user = _student(client)
    row = NotificationFactory.create(recipient=user, url=url)
    response = client.get(reverse("notifications:open", args=[row.pk]))
    assert response["Location"] == CENTER
    row.refresh_from_db()
    assert row.read_at is not None


def test_open_someone_elses_notification_is_404_and_unchanged(client: Any) -> None:
    _student(client)
    row = NotificationFactory.create()
    assert client.get(reverse("notifications:open", args=[row.pk])).status_code == 404
    row.refresh_from_db()
    assert row.read_at is None


def test_mark_all_read(client: Any) -> None:
    user = _student(client)
    NotificationFactory.create_batch(2, recipient=user)
    other = NotificationFactory.create()
    response = client.post(reverse("notifications:read-all"))
    assert response.status_code == 302 and response["Location"] == CENTER
    assert not Notification.objects.filter(recipient=user, read_at=None).exists()
    other.refresh_from_db()
    assert other.read_at is None
    html = client.get(CENTER).content.decode()
    assert 'aria-label="Notifications"' in html
    assert "Mark all as read" not in html


def test_bell_shows_unread_count_on_student_pages(client: Any) -> None:
    user = _student(client)
    NotificationFactory.create_batch(2, recipient=user)
    NotificationFactory.create(recipient=user, read_at=timezone.now())
    html = client.get("/me/").content.decode()
    assert 'aria-label="Notifications, 2 unread"' in html
    assert f'href="{CENTER}"' in html


def test_empty_center(client: Any) -> None:
    _student(client)
    assert "No notifications yet." in client.get(CENTER).content.decode()


def test_center_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    user = _student(client)
    NotificationFactory.create_batch(50, recipient=user)
    with django_assert_max_num_queries(8):
        assert client.get(CENTER).status_code == 200
