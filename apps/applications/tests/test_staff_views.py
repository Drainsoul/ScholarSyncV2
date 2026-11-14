from datetime import timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

S = Application.Status


def _staff(slug: str = "tcu-ceaa") -> Any:
    program = ProgramFactory.create(slug=slug, name=slug.upper())
    return MembershipFactory.create(program=program, user__verified=True)


def _row(program: Any, status: str = S.SUBMITTED, days_ago: int = 0, **kwargs: Any) -> Application:
    when = timezone.now() - timedelta(days=days_ago)
    return ApplicationFactory.create(
        program=program, status=status, submitted_at=when, first_submitted_at=when, **kwargs
    )


def _url(slug: str = "tcu-ceaa") -> str:
    return reverse("review:queue", kwargs={"program": slug})


def test_queue_lists_waiting_by_default_oldest_first(client: Any) -> None:
    membership = _staff()
    program = membership.program
    newer = _row(program, days_ago=1, profile=ProfileFactory.create(first_name="Newer"))
    older = _row(program, days_ago=5, profile=ProfileFactory.create(first_name="Older"))
    _row(program, S.APPROVED, profile=ProfileFactory.create(first_name="Decided"))
    client.force_login(membership.user)
    response = client.get(_url())
    assert response.status_code == 200
    rows = [row["application"] for row in response.context["rows"]]
    assert rows == [older, newer]
    body = response.content.decode()
    assert "Older" in body and "Decided" not in body
    assert response.context["total"] == 2


def test_queue_odd_params_answer_200(client: Any) -> None:
    membership = _staff()
    program = membership.program
    waiting = _row(program)
    ApplicationFactory.create(program=program, status=S.DRAFT)
    ApplicationFactory.create(program=program, status=S.WITHDRAWN, submitted_at=None)
    _row(ProgramFactory.create(slug="lani"))
    client.force_login(membership.user)
    response = client.get(
        _url(), {"status": "nope", "sort": "bogus", "page": "999", "term": "abc", "q": "%_"}
    )
    assert response.status_code == 200
    assert response.context["filters"].status == "waiting"
    assert response.context["total"] == 0
    response = client.get(_url(), {"status": "nope", "sort": "bogus", "page": "999", "term": "abc"})
    assert [r["application"] for r in response.context["rows"]] == [waiting]


def test_queue_htmx_renders_only_the_table(client: Any) -> None:
    membership = _staff()
    _row(membership.program)
    client.force_login(membership.user)
    full = client.get(_url())
    assert "<html" in full.content.decode()
    response = client.get(_url(), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="queue-table")
    body = response.content.decode()
    assert "<html" not in body
    assert 'id="queue-table"' in body
    assert 'id="queue-count"' in body and "hx-swap-oob" in body
    vary = response["Vary"]
    assert "HX-Request" in vary and "HX-Target" in vary


def test_queue_query_budget(client: Any, django_assert_max_num_queries: Any) -> None:
    membership = _staff()
    for index in range(30):
        _row(membership.program, days_ago=index)
    client.force_login(membership.user)
    with django_assert_max_num_queries(12):
        response = client.get(_url())
    assert len(response.context["rows"]) == 25


def test_staff_nav_shows_applications_count(client: Any) -> None:
    membership = _staff()
    _row(membership.program)
    _row(membership.program, S.UNDER_REVIEW)
    client.force_login(membership.user)
    response = client.get(reverse("workspace:dashboard", kwargs={"program": "tcu-ceaa"}))
    nav = response.context["nav_items"]
    assert [item["label"] for item in nav] == ["Dashboard", "Applications", "Students"]
    assert nav[1]["count"] == 1
    assert nav[1]["url"] == _url()


def test_lani_staff_get_403_on_tcu_queue(client: Any) -> None:
    ProgramFactory.create(slug="tcu-ceaa")
    lani = _staff("lani")
    client.force_login(lani.user)
    assert client.get(_url()).status_code == 403
