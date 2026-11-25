import re
from typing import Any

import pytest
from django.contrib.sessions.models import Session
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.core.tests.auth import reauthenticated, replay_after_password, signed_in_long_ago
from apps.programs.tests.factories import MembershipFactory
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

LIST = "/office/staff/"
NEW = "/office/staff/new/"
NEW_PASSWORD = "a-brand-new-pass-2026"


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True, full_name="Jessica Tate")
    reauthenticated(client, user)
    return user


def _create(client: Any, **data: str) -> Any:
    form = {"full_name": "Ana Reyes", "email": "Ana.Reyes@Example.com", "role": "staff"}
    form.update(data)
    return client.post(NEW, form)


def _active(client: Any, user: User, active: bool) -> Any:
    url = reverse("office:staff-active", args=[user.pk])
    return client.post(url, {"active": "1" if active else "0"}, follow=True)


def test_create_account_sends_welcome_with_working_link(client: Any, office: User) -> None:
    response = _create(client)
    user = User.objects.get(email="ana.reyes@example.com")
    assert response.status_code == 302
    assert response["Location"] == reverse("office:staff-detail", args=[user.pk])
    assert (user.role, user.full_name, user.has_usable_password()) == (
        User.Role.STAFF,
        "Ana Reyes",
        False,
    )
    mail = EmailOutbox.objects.get(kind="staff_welcome")
    assert mail.to == user.email
    assert mail.context["role_label"] == "Program staff"
    link = mail.context["set_password_url"]
    path = re.sub(r"^https?://[^/]+", "", link)
    stranger = type(client)()
    page = stranger.get(path, follow=True)
    form_url = page.redirect_chain[-1][0] if page.redirect_chain else path
    done = stranger.post(form_url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert done.status_code == 302
    assert type(client)().login(email=user.email, password=NEW_PASSWORD)


def test_existing_email_is_a_form_error(client: Any, office: User) -> None:
    UserFactory.create(email="ana.reyes@example.com")
    response = _create(client, email="ANA.REYES@example.com")
    assert response.status_code == 200
    assert "An account with this email already exists." in response.content.decode()
    assert User.objects.filter(email__iexact="ana.reyes@example.com").count() == 1


def test_full_name_required(client: Any, office: User) -> None:
    assert _create(client, full_name="  ").status_code == 200
    assert not User.objects.filter(email="ana.reyes@example.com").exists()


def test_create_needs_reauthentication(client: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    signed_in_long_ago(client, office)
    response = _create(client)
    assert not User.objects.filter(email="ana.reyes@example.com").exists()
    replay_after_password(client, response)
    assert User.objects.filter(email="ana.reyes@example.com").count() == 1


def test_deactivate_ends_sessions_and_blocks_sign_in(client: Any, office: User) -> None:
    other_office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    staff = UserFactory.create(role=User.Role.STAFF, verified=True)
    staff_client = type(client)()
    staff_client.force_login(staff)
    assert Session.objects.count() == 2
    response = _active(client, staff, False)
    assert "Account deactivated." in response.content.decode()
    staff.refresh_from_db()
    assert not staff.is_active
    assert staff_client.get("/staff/").status_code == 302  # signed out
    assert Session.objects.count() == 1
    assert other_office.is_active
    _active(client, staff, True)
    assert User.objects.get(pk=staff.pk).is_active
    actions = list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))
    assert actions[-2:] == ["user.deactivated", "user.reactivated"]


def test_cannot_deactivate_self_but_another_office_can(client: Any, office: User) -> None:
    """The only office account can't lock itself out; a second one can
    deactivate the first, which is then signed out and can't sign in."""
    html = _active(client, office, False).content.decode().replace("&#x27;", "'")
    assert "You can't deactivate your own account." in html
    office.refresh_from_db()
    assert office.is_active
    second = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    second_client = reauthenticated(type(client)(), second)
    _active(second_client, office, False)
    assert not User.objects.get(pk=office.pk).is_active
    assert client.get("/office/").status_code == 302  # the first office was signed out


def test_resend_welcome_only_before_first_sign_in(client: Any, office: User) -> None:
    _create(client)
    user = User.objects.get(email="ana.reyes@example.com")
    detail = client.get(reverse("office:staff-detail", args=[user.pk])).content.decode()
    assert "Send the set-password email again" in detail
    client.post(reverse("office:staff-welcome", args=[user.pk]))
    assert EmailOutbox.objects.filter(kind="staff_welcome").count() == 2
    User.objects.filter(pk=user.pk).update(last_login="2026-11-17T09:00:00+08:00")
    detail = client.get(reverse("office:staff-detail", args=[user.pk])).content.decode()
    assert "Send the set-password email again" not in detail
    client.post(reverse("office:staff-welcome", args=[user.pk]))
    assert EmailOutbox.objects.filter(kind="staff_welcome").count() == 2


def test_audit_data_has_no_email_or_name(client: Any, office: User) -> None:
    _create(client)
    user = User.objects.get(email="ana.reyes@example.com")
    _active(client, user, False)
    for event in AuditEvent.objects.filter(action__startswith="user."):
        assert "ana" not in str(event.data).lower()


def test_students_are_not_listed_and_accounts_404_for_students(client: Any, office: User) -> None:
    student = UserFactory.create(full_name="Stu Dent")
    html = client.get(LIST).content.decode()
    assert "Stu Dent" not in html
    assert client.get(reverse("office:staff-detail", args=[student.pk])).status_code == 404


def test_staff_list_search_and_query_count(
    client: Any, office: User, django_assert_max_num_queries: Any
) -> None:
    for n in range(50):
        # Own emails: a sequence email like user107@ would also match the "07" in the search.
        MembershipFactory.create(
            user__full_name=f"Person {n:02d}",
            user__email=f"staff-{n:02d}@scholarsync.test",
            user__verified=True,
        )
    with django_assert_max_num_queries(12):
        html = client.get(LIST + "?q=Person 07").content.decode()
    assert "Person 07" in html and "Person 08" not in html
