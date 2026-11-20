import html

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.models import AcademicTerm
from apps.programs.tests.factories import AcademicTermFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def office(client):
    user = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    client.force_login(user)
    return user


def text(response) -> str:
    return html.unescape(response.content.decode())


def test_terms_page_lists_and_marks_current(client, office) -> None:
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    later = AcademicTermFactory.create(school_year_start=2026, term=2)
    earlier = AcademicTermFactory.create(school_year_start=2025, term=2)
    page = text(client.get(reverse("office:terms")))
    for term in (current, later, earlier):
        assert str(term) in page
    assert "Current" in page
    assert reverse("office:terms-current", args=[later.pk]) in page
    assert reverse("office:terms-current", args=[earlier.pk]) not in page
    assert reverse("office:terms-current", args=[current.pk]) not in page
    assert "Add school year 2027–2028" in page


def test_terms_page_query_budget(client, office, django_assert_max_num_queries) -> None:
    for year in range(2020, 2027):
        AcademicTermFactory.create(school_year_start=year, term=1)
    with django_assert_max_num_queries(9):  # + the Tasks nav count (rev 27)
        assert client.get(reverse("office:terms")).status_code == 200


def test_add_year_post(client, office) -> None:
    AcademicTermFactory.create(school_year_start=2026, term=1)
    response = client.post(reverse("office:terms-add"))
    assert response.status_code == 302
    assert AcademicTerm.objects.filter(school_year_start=2027).count() == 3


def test_add_year_post_first_ever_uses_this_year(client, office) -> None:
    client.post(reverse("office:terms-add"))
    assert AcademicTerm.objects.count() == 3


def test_current_confirm_page_and_post(client, office) -> None:
    AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    later = AcademicTermFactory.create(school_year_start=2026, term=2)
    url = reverse("office:terms-current", args=[later.pk])
    page = text(client.get(url))
    assert f"Make {later} the current term" in page
    response = client.post(url, follow=True)
    later.refresh_from_db()
    assert later.is_current
    assert f"{later} is now the current term." in text(response)


def test_current_post_backward_shows_error(client, office) -> None:
    earlier = AcademicTermFactory.create(school_year_start=2025, term=2)
    AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    response = client.post(reverse("office:terms-current", args=[earlier.pk]), follow=True)
    assert "The current term can only move forward." in text(response)
    earlier.refresh_from_db()
    assert not earlier.is_current


def test_nav_has_terms(client, office) -> None:
    page = text(client.get(reverse("office:home")))
    assert f'href="{reverse("office:terms")}"' in page
