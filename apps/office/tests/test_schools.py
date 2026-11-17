from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import School
from apps.programs.tests.factories import SchoolFactory

pytestmark = pytest.mark.django_db

LIST = "/office/schools/"


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    client.force_login(user)
    return user


def _data(**changes: str) -> dict[str, str]:
    data = {
        "name": "Technological University of the Philippines",
        "type": "suc",
        "grading_scale": "one_to_five",
        "is_in_taguig": "",
    }
    data.update(changes)
    return data


def test_add_and_edit_school_audits(client: Any, office: User) -> None:
    response = client.post(reverse("office:school-new"), _data(), follow=True)
    assert "School added." in response.content.decode()
    school = School.objects.get(name="Technological University of the Philippines")
    assert (school.type, school.grading_scale, school.is_in_taguig) == (
        "suc",
        "one_to_five",
        False,
    )
    client.post(reverse("office:school-edit", args=[school.pk]), _data(is_in_taguig="on"))
    school.refresh_from_db()
    assert school.is_in_taguig
    actions = list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))
    assert actions == ["school.added", "school.updated"]
    assert "Technological" not in str(AuditEvent.objects.first().data)  # type: ignore[union-attr]


def test_school_name_clash_any_case(client: Any, office: User) -> None:
    SchoolFactory.create(name="Taguig City University")
    response = client.post(reverse("office:school-new"), _data(name="taguig city UNIVERSITY"))
    assert "A school with this name already exists." in response.content.decode()
    assert School.objects.filter(name__iexact="taguig city university").count() == 1


def test_unknown_school_404(client: Any, office: User) -> None:
    assert client.get(reverse("office:school-edit", args=[999999])).status_code == 404


def test_school_nav_item(client: Any, office: User) -> None:
    response = client.get(LIST)
    labels = [item["label"] for item in response.context["nav_items"]]
    assert labels.index("Staff") < labels.index("Schools") < labels.index("Terms")


def test_schools_list_search_and_query_count(
    client: Any, office: User, django_assert_max_num_queries: Any
) -> None:
    for n in range(50):
        SchoolFactory.create(name=f"School {n:02d}")
    with django_assert_max_num_queries(10):
        html = client.get(LIST + "?q=School 07").content.decode()
    assert "School 07" in html and "School 08" not in html
