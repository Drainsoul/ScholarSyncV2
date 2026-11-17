import json
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.applications import review
from apps.applications.models import Application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.awards.models import Award
from apps.awards.tests.factories import AwardFactory
from apps.core.audit import record
from apps.core.models import AuditEvent
from apps.matching.checklist import CHECK_LABELS
from apps.programs.tests.factories import BenefitTierFactory, MembershipFactory, ProgramFactory
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
    assert [item["label"] for item in nav] == [
        "Dashboard",
        "Applications",
        "Scholars",
        "Disbursements",
        "Students",
    ]
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
    timeline = body.split('class="timeline"', 1)[1]
    assert re.search(r'timeline__what">Submitted</p>\s*<p[^>]*>.*?by Student', timeline, re.S)
    assert re.search(
        rf'timeline__what">[^<]* approved</p>\s*<p[^>]*>.*?by {membership.user.full_name}',
        timeline,
        re.S,
    )
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


def test_review_page_shows_earlier_return_reason_on_a_resubmission(client: Any) -> None:
    membership = _staff()
    program = membership.program
    client.force_login(membership.user)
    first = _row(program, S.SUBMITTED)
    assert "Returned earlier" not in client.get(_detail_url(first.pk)).content.decode()
    for status in (S.SUBMITTED, S.UNDER_REVIEW):
        again = _row(program, status, decision_reason="Scan is <blurry>")
        body = client.get(_detail_url(again.pk)).content.decode()
        assert "Returned earlier: Scan is &lt;blurry&gt;" in body
        assert "<blurry>" not in body


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


def test_review_page_without_user_hides_email_and_income_is_not_given(client: Any) -> None:
    membership = _staff()
    profile = ProfileFactory.create(user=None, monthly_household_income=None)
    application = _row(membership.program, profile=profile)
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "<dt>Email</dt>" not in body
    assert "Not given" in body and "— a month" not in body


# review actions


def _approvable(program: Any) -> Application:
    application = _row(program, S.UNDER_REVIEW)
    application.requested_tier = BenefitTierFactory.create(
        program=program, effective_from=application.term
    )
    application.save(update_fields=["requested_tier"])
    _with_document(application, "approved")
    return application


def _shown(response: Any) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def _post(client: Any, name: str, application: Application, **extra: Any) -> Any:
    kwargs: dict[str, Any] = {"program": "tcu-ceaa", "pk": application.pk}
    if "document" in extra:
        kwargs["document"] = extra.pop("document")
    return client.post(reverse(f"review:{name}", kwargs=kwargs), extra)


def test_start_review_succeeds_with_message(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program)
    client.force_login(membership.user)
    response = _post(client, "start", application)
    assert response.status_code == 302
    assert response["Location"] == _detail_url(application.pk)
    assert _shown(response) == ["Review started."]
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW
    assert AuditEvent.objects.filter(action="application.review_started").count() == 1


def test_review_page_posts_to_the_action_urls(client: Any) -> None:
    membership = _staff()
    submitted = _row(membership.program)
    reviewing = _row(membership.program, S.UNDER_REVIEW)
    document = _with_document(reviewing)
    client.force_login(membership.user)
    body = client.get(_detail_url(submitted.pk)).content.decode()
    assert reverse("review:start", args=["tcu-ceaa", submitted.pk]) in body
    response = client.get(_detail_url(reviewing.pk))
    body = response.content.decode()
    assert reverse("review:document-approve", args=["tcu-ceaa", reviewing.pk, document.pk]) in body
    assert reverse("review:document-decline", args=["tcu-ceaa", reviewing.pk, document.pk]) in body
    assert reverse("review:decide", args=["tcu-ceaa", reviewing.pk]) in body
    decision = body.split('id="decision-title"')[1].split("</section>")[0]
    assert "disabled" not in decision
    assert "disabled" not in body.split("<tbody>")[1].split("</tbody>")[0]


def test_second_start_review_shows_error_with_400(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    client.force_login(membership.user)
    response = _post(client, "start", application)
    assert response.status_code == 400
    body = response.content.decode()
    assert "Someone has already started reviewing this application." in body
    assert "banner--danger" in body


def test_approve_document_succeeds_with_message(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    document = _with_document(application)
    client.force_login(membership.user)
    response = _post(client, "document-approve", application, document=document.pk)
    assert response.status_code == 302
    assert _shown(response) == ["Document approved."]
    document.refresh_from_db()
    assert document.status == "approved"
    again = _post(client, "document-approve", application, document=document.pk)
    assert again.status_code == 400  # a double click is refused with a sentence


def test_decide_approve_creates_award(client: Any) -> None:
    membership = _staff()
    application = _approvable(membership.program)
    client.force_login(membership.user)
    page = client.get(_detail_url(application.pk))
    assert page.context["decision_form"].fields["tier"].initial == application.requested_tier_id
    response = _post(
        client, "decide", application, decision="approve", tier=application.requested_tier_id
    )
    assert response.status_code == 302
    assert _shown(response) == ["Application approved. The award has been created."]
    application.refresh_from_db()
    assert application.status == S.APPROVED
    assert Award.objects.filter(source_application=application).count() == 1


def test_decide_approve_with_a_tier_not_in_force_shows_form_error(client: Any) -> None:
    membership = _staff()
    application = _approvable(membership.program)
    tier = application.requested_tier
    assert tier is not None
    other = BenefitTierFactory.create(program=membership.program, effective_from=application.term)
    tier.is_active = False
    tier.save()
    client.force_login(membership.user)
    response = _post(client, "decide", application, decision="approve", tier=tier.pk)
    assert response.status_code == 400
    assert "tier" in response.context["decision_form"].errors
    ok = _post(client, "decide", application, decision="approve", tier=other.pk)
    assert ok.status_code == 302


def test_decide_approve_with_undecided_document_shows_service_error(client: Any) -> None:
    membership = _staff()
    application = _approvable(membership.program)
    _with_document(application)  # a pending one
    client.force_login(membership.user)
    response = _post(
        client, "decide", application, decision="approve", tier=application.requested_tier_id
    )
    assert response.status_code == 400
    assert "Approve or decline every document first" in response.content.decode()
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW


def test_decide_return_and_reject(client: Any) -> None:
    membership = _staff()
    returned = _row(membership.program, S.UNDER_REVIEW)
    rejected = _row(membership.program, S.UNDER_REVIEW)
    client.force_login(membership.user)
    response = _post(client, "decide", returned, decision="return", reason="Blurry scan.")
    assert response.status_code == 302
    assert _shown(response) == ["Application returned to the student."]
    response = _post(client, "decide", rejected, decision="reject", reason="Out of area.")
    assert _shown(response)[-1] == "Application not approved."
    returned.refresh_from_db()
    rejected.refresh_from_db()
    assert (returned.status, rejected.status) == (S.RETURNED, S.REJECTED)


def test_decide_without_reason_rerenders_bound_form_with_400(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    client.force_login(membership.user)
    response = _post(client, "decide", application, decision="return", reason="")
    assert response.status_code == 400
    assert "Say what the student needs to fix." in response.content.decode()
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW


def test_decide_failure_rerenders_with_400_and_fresh_state(client: Any) -> None:
    membership = _staff()
    colleague = MembershipFactory.create(program=membership.program, user__verified=True)
    application = _row(membership.program, S.UNDER_REVIEW)
    client.force_login(membership.user)
    assert client.get(_detail_url(application.pk)).status_code == 200  # the form is on screen
    review.return_application(
        actor=colleague.user,
        program=membership.program,
        application=application,
        reason="Missing page.",
    )
    response = _post(client, "decide", application, decision="reject", reason="Out of area.")
    assert response.status_code == 400
    body = response.content.decode()
    assert "banner--danger" in body
    assert "Returned: Missing page." in body  # fresh state, not the stale form
    assert 'name="decision"' not in body
    application.refresh_from_db()
    assert application.status == S.RETURNED
    assert AuditEvent.objects.filter(action="application.rejected").count() == 0


def test_decline_dialog_htmx_and_full_page(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    document = _with_document(application)
    url = reverse("review:document-decline", args=["tcu-ceaa", application.pk, document.pk])
    client.force_login(membership.user)
    fragment = client.get(url, HTTP_HX_REQUEST="true")
    assert fragment.status_code == 200
    assert "dialog__header" in fragment.content.decode()
    assert "<html" not in fragment.content.decode()
    assert "HX-Request" in fragment["Vary"]
    page = client.get(url)
    assert "<html" in page.content.decode() and "dialog__header" not in page.content.decode()

    empty = client.post(url, {"reason": ""}, HTTP_HX_REQUEST="true")
    assert empty.status_code == 200
    assert "Say why you&#x27;re declining this document." in empty.content.decode()
    assert "<html" not in empty.content.decode()
    document.refresh_from_db()
    assert document.status == "pending"

    ok = client.post(url, {"reason": "Blurry."}, HTTP_HX_REQUEST="true")
    assert ok.status_code == 204
    assert ok["HX-Refresh"] == "true"
    assert "closeDialog" in json.loads(ok["HX-Trigger"])
    assert _shown(ok) == ["Document declined."]
    document.refresh_from_db()
    assert document.status == "declined" and document.decline_reason == "Blurry."


def test_decline_without_htmx_redirects_with_message(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    document = _with_document(application)
    url = reverse("review:document-decline", args=["tcu-ceaa", application.pk, document.pk])
    client.force_login(membership.user)
    page = client.post(url, {"reason": ""})
    assert page.status_code == 200 and "<html" in page.content.decode()
    response = client.post(url, {"reason": "Blurry."})
    assert response.status_code == 302
    assert response["Location"] == _detail_url(application.pk)
    assert _shown(response) == ["Document declined."]


def test_decline_of_approved_document_shows_error_in_dialog(client: Any) -> None:
    membership = _staff()
    application = _row(membership.program, S.UNDER_REVIEW)
    document = _with_document(application, "approved")
    url = reverse("review:document-decline", args=["tcu-ceaa", application.pk, document.pk])
    client.force_login(membership.user)
    response = client.post(url, {"reason": "Changed my mind."}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert "banner--danger" in response.content.decode()
    document.refresh_from_db()
    assert document.status == "approved"


def test_actions_on_another_programs_application_404_and_change_nothing(client: Any) -> None:
    membership = _staff()
    foreign = _row(ProgramFactory.create(slug="lani"), S.UNDER_REVIEW)
    foreign_doc = _with_document(foreign)
    mine = _row(membership.program, S.UNDER_REVIEW)
    mine_doc = _with_document(mine)
    client.force_login(membership.user)
    before = AuditEvent.objects.count()
    slug = "tcu-ceaa"
    calls = [
        client.post(reverse("review:start", args=[slug, foreign.pk])),
        client.post(reverse("review:document-approve", args=[slug, foreign.pk, foreign_doc.pk])),
        client.post(reverse("review:document-approve", args=[slug, mine.pk, foreign_doc.pk])),
        client.get(reverse("review:document-decline", args=[slug, foreign.pk, foreign_doc.pk])),
        client.get(reverse("review:document-decline", args=[slug, mine.pk, foreign_doc.pk])),
        client.post(
            reverse("review:document-decline", args=[slug, mine.pk, foreign_doc.pk]),
            {"reason": "No."},
        ),
        client.post(
            reverse("review:decide", args=[slug, foreign.pk]),
            {"decision": "reject", "reason": "No."},
        ),
    ]
    assert [r.status_code for r in calls] == [404] * 7
    for row in (foreign, mine):
        row.refresh_from_db()
        assert row.status == S.UNDER_REVIEW
    foreign_doc.refresh_from_db()
    mine_doc.refresh_from_db()
    assert foreign_doc.status == mine_doc.status == "pending"
    assert AuditEvent.objects.count() == before


def test_decide_invalid_form_after_colleague_moved_it_explains(client: Any) -> None:
    membership = _staff()
    colleague = MembershipFactory.create(program=membership.program, user__verified=True)
    application = _row(membership.program, S.UNDER_REVIEW)
    review.return_application(
        actor=colleague.user,
        program=membership.program,
        application=application,
        reason="Missing page.",
    )
    client.force_login(membership.user)
    response = _post(client, "decide", application, decision="reject", reason="")
    assert response.status_code == 400
    assert "This application is no longer under review." in response.content.decode()


# bulk


def _bulk_url(slug: str = "tcu-ceaa") -> str:
    return reverse("review:bulk", kwargs={"program": slug})


def test_bulk_view_htmx_refreshes_and_queues_messages(client: Any) -> None:
    membership = _staff()
    program = membership.program
    waiting = [_row(program, profile=ProfileFactory.create()) for _ in range(2)]
    started = _row(program, S.UNDER_REVIEW, profile=ProfileFactory.create(first_name="Already"))
    client.force_login(membership.user)
    response = client.post(
        _bulk_url(),
        {"ids": [r.pk for r in (*waiting, started)], "action": "start_review"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    assert response["HX-Refresh"] == "true"
    assert "HX-Trigger" not in response
    texts = _shown(response)
    assert texts[0] == "Started review of 2 applications. Skipped 1."
    assert (
        texts[1]
        == f"{started.profile.full_name}: Someone has already started reviewing this application."
    )
    for row in waiting:
        row.refresh_from_db()
        assert row.status == S.UNDER_REVIEW


def test_bulk_view_full_page_redirects_with_messages(client: Any) -> None:
    membership = _staff()
    row = _approvable(membership.program)
    client.force_login(membership.user)
    response = client.post(_bulk_url(), {"ids": [row.pk], "action": "approve"})
    assert response.status_code == 302
    assert response["Location"] == _url()
    assert _shown(response) == ["Approved 1 application."]
    row.refresh_from_db()
    assert row.status == S.APPROVED


def test_bulk_view_full_page_redirect_keeps_the_queue_filters(client: Any) -> None:
    membership = _staff()
    row = _row(membership.program, profile=ProfileFactory.create(first_name="Ana"))
    client.force_login(membership.user)
    body = client.get(_url(), {"status": "submitted", "q": "Ana", "evil": "x"}).content.decode()
    assert 'name="next_query" value="status=submitted&amp;q=Ana"' in body
    response = client.post(
        _bulk_url(),
        {"ids": [row.pk], "action": "start_review", "next_query": "status=submitted&q=Ana&x=1"},
    )
    assert response.status_code == 302
    assert response["Location"] == _url() + "?status=submitted&q=Ana"
    refused = client.post(_bulk_url(), {"action": "approve", "next_query": "q=Ana"})
    assert refused["Location"] == _url() + "?q=Ana"


def test_bulk_view_next_query_is_never_a_url(client: Any) -> None:
    membership = _staff()
    row = _row(membership.program)
    client.force_login(membership.user)
    for hostile in ("https://evil.example/", "//evil.example", "/admin/?q=x", "\evil"):
        response = client.post(
            _bulk_url(), {"ids": [row.pk], "action": "start_review", "next_query": hostile}
        )
        assert response["Location"] == _url(), hostile


def test_bulk_view_needs_a_selection_and_an_action(client: Any) -> None:
    membership = _staff()
    row = _row(membership.program)
    client.force_login(membership.user)
    none = client.post(_bulk_url(), {"action": "approve"})
    assert _shown(none) == ["Select at least one application first."]
    client.get(_url())  # shows (and so clears) the queued message
    no_action = client.post(_bulk_url(), {"ids": [row.pk]})
    assert _shown(no_action) == ["Choose an action for the selected applications."]
    client.get(_url())
    htmx = client.post(_bulk_url(), {"action": "approve"}, HTTP_HX_REQUEST="true")
    assert htmx.status_code == 204 and "HX-Refresh" not in htmx
    assert json.loads(htmx["HX-Trigger"])["toast"] == {
        "message": "Select at least one application first.",
        "tone": "warning",
    }
    row.refresh_from_db()
    assert row.status == S.SUBMITTED


def test_bulk_view_over_100_is_refused(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    response = client.post(_bulk_url(), {"ids": list(range(1, 102)), "action": "start_review"})
    assert _shown(response) == ["Choose at most 100 applications at a time."]


def test_queue_offers_bulk_form_and_approve_only_when_waiting(client: Any) -> None:
    membership = _staff()
    _row(membership.program)
    _row(membership.program, S.APPROVED)
    client.force_login(membership.user)
    body = client.get(_url()).content.decode()
    assert "data-bulk" in body and 'name="ids"' in body
    assert 'value="approve"' in body
    approved = client.get(_url(), {"status": "approved"}).content.decode()
    assert 'value="approve"' not in approved
    assert 'value="start_review"' in approved
    submitted = client.get(_url(), {"status": "submitted"}).content.decode()
    assert 'value="approve"' not in submitted  # approval needs a review first
    _row(membership.program, S.UNDER_REVIEW)
    reviewing = client.get(_url(), {"status": "under_review"}).content.decode()
    assert 'value="approve"' in reviewing


# --- on-behalf applications on the review screen ---


def _behalf_snapshot(override: list[str]) -> dict[str, Any]:
    snapshot = _snapshot()
    snapshot["filed_by_staff"] = True
    snapshot["override"] = override
    return snapshot


def test_review_shows_filed_by_staff(client: Any) -> None:
    membership = _staff()
    application = _row(
        membership.program,
        S.UNDER_REVIEW,
        on_behalf=True,
        created_by=membership.user,
        match_snapshot=_behalf_snapshot([]),
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert f"Filed by {membership.user.full_name} for the student." in body
    application.created_by = None
    application.save()
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Filed by staff for the student." in body


def test_review_lists_overridden_checks_with_reason(client: Any) -> None:
    membership = _staff()
    application = _row(
        membership.program,
        S.UNDER_REVIEW,
        on_behalf=True,
        created_by=membership.user,
        override_reason="Voter record <b>pending</b> at the COMELEC",
        match_snapshot=_behalf_snapshot(["voter"]),
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Overridden by staff" in body
    block = body.split("Overridden by staff", 1)[1]
    assert "Voter record &lt;b&gt;pending&lt;/b&gt; at the COMELEC" in block
    assert "<b>pending</b>" not in body
    assert CHECK_LABELS["voter"] in block


def test_review_eligible_on_behalf_has_no_override_block(client: Any) -> None:
    membership = _staff()
    application = _row(
        membership.program,
        S.UNDER_REVIEW,
        on_behalf=True,
        created_by=membership.user,
        match_snapshot=_behalf_snapshot([]),
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Filed by" in body
    assert "Overridden by staff" not in body


def test_returned_on_behalf_links_fix_and_resubmit(client: Any) -> None:
    membership = _staff()
    application = _row(
        membership.program,
        S.RETURNED,
        on_behalf=True,
        created_by=membership.user,
        decision_reason="Scan is blurry",
        match_snapshot=_behalf_snapshot([]),
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    url = reverse(
        "review:behalf", kwargs={"program": membership.program.slug, "pk": application.pk}
    )
    assert f'href="{url}"' in body
    assert "Fix and resubmit" in body


def test_student_application_review_unchanged(client: Any) -> None:
    membership = _staff()
    application = _row(
        membership.program, S.RETURNED, decision_reason="Scan is blurry", match_snapshot=_snapshot()
    )
    client.force_login(membership.user)
    body = client.get(_detail_url(application.pk)).content.decode()
    assert "Filed by" not in body
    assert "Overridden by staff" not in body
    assert "Fix and resubmit" not in body
