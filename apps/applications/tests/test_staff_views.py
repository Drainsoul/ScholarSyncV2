from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.applications.models import Application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.awards.tests.factories import AwardFactory
from apps.core.audit import record
from apps.core.models import AuditEvent
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.students.tests.factories import FullProfileFactory, ProfileFactory

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


# --- the review screen ---


def _detail_url(pk: int, slug: str = "tcu-ceaa") -> str:
    return reverse("review:detail", kwargs={"program": slug, "pk": pk})


def _snapshot() -> dict[str, Any]:
    return {
        "version": 1,
        "evaluated_on": "2026-11-03",
        "eligible": True,
        "checks": [
            {"code": "gwa", "state": "met", "reason": ""},
            {"code": "voter", "state": "unmet", "reason": "Not a registered voter."},
        ],
        "hint": {
            "label": "Priority tier",
            "program": "tcu-ceaa",
            "merit": False,
            "probability": 0.8,
        },
    }


def _with_document(application: Application, status: str = "pending", versions: int = 1) -> Any:
    document = DocumentFactory.create(application=application, status=status)
    for version in range(1, versions + 1):
        DocumentFileFactory.create(
            document=document, version=version, is_current=version == versions
        )
    return document


def test_review_page_shows_snapshot_documents_and_history(client: Any) -> None:
    membership = _staff()
    profile = FullProfileFactory.create(first_name="Ana", last_name="Reyes")
    application = _row(
        membership.program,
        S.UNDER_REVIEW,
        profile=profile,
        match_snapshot=_snapshot(),
        school_name="TUP Taguig",
        course="BSIT",
        year_level=2,
        gwa=Decimal("88.50"),
        gwa_scale="percent",
    )
    document = _with_document(application, versions=2)
    approved = _with_document(application, "approved")
    record(actor=profile.user, action="application.submitted", target=application)
    record(actor=membership.user, action="document.approved", target=approved)
    client.force_login(membership.user)
    response = client.get(_detail_url(application.pk))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Ana Reyes" in body and "TUP Taguig" in body and "BSIT" in body
    assert "88.50" in body
    assert "As checked on 3 November 2026" in body
    assert "1 of 2 rules met" in body
    assert "Not a registered voter." in body
    assert "Legacy model suggests: Priority tier" in body
    assert "Advisory only. The rules above decided who could apply." in body
    assert "1 of 2 documents approved" in body
    assert "version 2" in body
    assert reverse("files:download", args=[document.files.get(is_current=True).file_id]) in body
    assert "Submitted" in body and "by Student" in body
    assert "approved" in body and membership.user.full_name in body
    assert response.context["position"].position == 1


def test_review_page_income_is_monthly(client: Any) -> None:
    membership = _staff()
    profile = FullProfileFactory.create(monthly_household_income=Decimal("25000.00"))
    application = _row(membership.program, profile=profile)
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Household income" in body
    assert "₱25,000.00 a month" in body
    assert "a year" not in body


def test_review_page_notes_other_program_award(client: Any) -> None:
    membership = _staff()
    profile = ProfileFactory.create()
    application = _row(membership.program, profile=profile)
    other = ProgramFactory.create(slug="lani", name="LANI")
    AwardFactory.create(
        source_application=ApplicationFactory.create(
            profile=profile, program=other, status=S.APPROVED
        )
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Also holds an active LANI award." in body


def test_review_page_buttons_follow_status(client: Any) -> None:
    membership = _staff()
    program = membership.program
    client.force_login(membership.user)
    submitted = _row(program, S.SUBMITTED)
    _with_document(submitted)
    body = client.get(_detail_url(submitted.pk)).content.decode()
    assert "Start review" in body and ">Approve<" not in body
    reviewing = _row(program, S.UNDER_REVIEW)
    _with_document(reviewing)
    body = client.get(_detail_url(reviewing.pk)).content.decode()
    assert ">Approve<" in body and "Decline" in body and "Start review" not in body
    approved = _row(program, S.APPROVED, decided_at=timezone.now(), decided_by=membership.user)
    _with_document(approved, "approved")
    body = client.get(_detail_url(approved.pk)).content.decode()
    assert f"Approved by {membership.user.full_name} on" in body
    assert ">Approve<" not in body and "Start review" not in body
    returned = _row(program, S.RETURNED, decision_reason="Blurry scan")
    assert "Returned: Blurry scan" in client.get(_detail_url(returned.pk)).content.decode()
    rejected = _row(program, S.REJECTED, decision_reason="Out of area")
    assert "Not approved: Out of area" in client.get(_detail_url(rejected.pk)).content.decode()
    withdrawn = _row(program, S.WITHDRAWN)
    assert "Withdrawn by the student" in client.get(_detail_url(withdrawn.pk)).content.decode()


def test_review_page_query_budget(client: Any, django_assert_max_num_queries: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW, match_snapshot=_snapshot())
    for _ in range(8):
        _with_document(application)
    client.force_login(membership.user)
    with django_assert_max_num_queries(20):
        assert client.get(_detail_url(application.pk)).status_code == 200


def test_review_get_writes_nothing(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.SUBMITTED)
    client.force_login(membership.user)
    before = AuditEvent.objects.count()
    assert client.get(_detail_url(application.pk)).status_code == 200
    assert AuditEvent.objects.count() == before
    application.refresh_from_db()
    assert application.status == S.SUBMITTED


def test_review_page_other_program_is_404(client: Any) -> None:
    membership = _staff()
    other = _row(ProgramFactory.create(slug="lani"))
    client.force_login(membership.user)
    assert client.get(_detail_url(other.pk)).status_code == 404
    assert client.get(_detail_url(other.pk, "lani")).status_code == 403
