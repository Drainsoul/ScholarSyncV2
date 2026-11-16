from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.tests.factories import (
    AcademicTermFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

S = Application.Status


def _staff(slug: str = "tcu-ceaa") -> Any:
    program = ProgramFactory.create(slug=slug, name=slug.upper())
    return MembershipFactory.create(program=program, user__verified=True)


def _profile(program: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("user", None)
    return ProfileFactory.create(created_for=program, **kwargs)


def _url(slug: str = "tcu-ceaa") -> str:
    return reverse("review:behalf-new", kwargs={"program": slug})


def test_new_page_lists_in_progress_and_profiles(client: Any) -> None:
    membership = _staff()
    program = membership.program
    AcademicTermFactory.create(is_current=True)
    ana = _profile(program, first_name="Ana", last_name="Reyes")
    claimed = ProfileFactory.create(created_for=program, first_name="Claire", last_name="Cruz")
    ApplicationFactory.create(profile=ana, program=program, on_behalf=True)
    client.force_login(membership.user)
    response = client.get(_url())
    assert response.status_code == 200
    body = response.content.decode()
    assert "File for a student" in body
    assert "In progress" in body and "Continue" in body
    assert "Ana Reyes" in body and claimed.full_name in body
    assert "Claimed" in body and "Not claimed" in body
    assert "File an application" in body


def test_new_page_nothing_in_progress_and_empty_state(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    body = client.get(_url()).content.decode()
    assert "Nothing in progress." in body
    assert "No students yet. Add one on the Students page first." in body
    assert reverse("workspace:students-new", kwargs={"program": "tcu-ceaa"}) in body


def test_new_page_search(client: Any) -> None:
    membership = _staff()
    _profile(membership.program, first_name="Ana", last_name="Reyes")
    _profile(membership.program, first_name="Ben", last_name="Santos")
    client.force_login(membership.user)
    body = client.get(_url(), {"q": "santos"}).content.decode()
    assert "Ben Santos" in body and "Ana Reyes" not in body


def test_new_page_query_budget(client: Any, django_assert_max_num_queries: Any) -> None:
    membership = _staff()
    program = membership.program
    AcademicTermFactory.create(is_current=True)
    profiles = [_profile(program) for _ in range(30)]
    for profile in profiles[:5]:
        ApplicationFactory.create(profile=profile, program=program, on_behalf=True)
    client.force_login(membership.user)
    with django_assert_max_num_queries(12):
        response = client.get(_url())
    assert response.status_code == 200
    assert len(response.context["profile_rows"]) == 25


def test_start_redirects_to_filing_page(client: Any) -> None:
    membership = _staff()
    AcademicTermFactory.create(is_current=True)
    profile = _profile(membership.program)
    client.force_login(membership.user)
    response = client.post(_url(), {"profile": profile.pk})
    application = Application.objects.get(profile=profile)
    assert response.status_code == 302
    assert response.url == reverse(
        "review:behalf", kwargs={"program": "tcu-ceaa", "pk": application.pk}
    )
    assert f"Application started for {profile.full_name}." in [
        str(m) for m in get_messages(response.wsgi_request)
    ]


def test_start_refusal_shows_sentence(client: Any) -> None:
    membership = _staff()  # no current term, so the service refuses
    profile = _profile(membership.program)
    client.force_login(membership.user)
    response = client.post(_url(), {"profile": profile.pk})
    assert response.status_code == 400
    assert "Applications aren&#x27;t open" in response.content.decode()
    assert Application.objects.count() == 0


def test_start_other_program_profile_404(client: Any) -> None:
    membership = _staff()
    AcademicTermFactory.create(is_current=True)
    other = _profile(ProgramFactory.create(slug="lani"))
    client.force_login(membership.user)
    assert client.post(_url(), {"profile": other.pk}).status_code == 404
    assert Application.objects.count() == 0


@pytest.mark.parametrize("data", [{"profile": "abc"}, {}, {"profile": "99999999999"}])
def test_start_bad_profile_value(client: Any, data: dict[str, str]) -> None:
    membership = _staff()
    client.force_login(membership.user)
    response = client.post(_url(), data)
    assert response.status_code == 400
    assert "Choose a student." in response.content.decode()


def test_withdraw_redirects_with_toast(client: Any) -> None:
    membership = _staff()
    program = membership.program
    AcademicTermFactory.create(is_current=True)
    application = ApplicationFactory.create(
        profile=_profile(program), program=program, on_behalf=True
    )
    client.force_login(membership.user)
    response = client.post(
        reverse("review:behalf-withdraw", kwargs={"program": "tcu-ceaa", "pk": application.pk})
    )
    assert response.status_code == 302 and response.url == _url()
    assert "Application withdrawn." in [str(m) for m in get_messages(response.wsgi_request)]
    application.refresh_from_db()
    assert application.status == S.WITHDRAWN


def test_queue_has_file_for_a_student_button(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    body = client.get(reverse("review:queue", kwargs={"program": "tcu-ceaa"})).content.decode()
    assert _url() in body and "File for a student" in body


def test_students_list_has_file_link(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    body = client.get(
        reverse("workspace:students", kwargs={"program": "tcu-ceaa"})
    ).content.decode()
    assert _url() in body
