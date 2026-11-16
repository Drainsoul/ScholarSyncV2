"""Moving the current term and rolling applications and awards over (M9)."""

import html
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.review_selectors import history
from apps.applications.tests.factories import ApplicationFactory
from apps.awards import services
from apps.awards.models import Award
from apps.awards.selectors import RolloverResult, rollover_preview
from apps.awards.services import rollover, start_term
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm
from apps.programs.tests.factories import AcademicTermFactory, BenefitTierFactory, ProgramFactory

pytestmark = pytest.mark.django_db
S = Application.Status


def office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)


@pytest.fixture
def terms() -> tuple[AcademicTerm, AcademicTerm]:
    old = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    new = AcademicTermFactory.create(school_year_start=2026, term=2)
    return old, new


def application(term: AcademicTerm, status: str, **fields: object) -> Application:
    if status != S.DRAFT and status != S.WITHDRAWN:
        fields.setdefault("submitted_at", timezone.now())
    return ApplicationFactory.create(term=term, status=status, **fields)


def test_rollover_withdraws_old_drafts_and_returned(terms) -> None:
    old, new = terms
    draft = application(old, S.DRAFT)
    returned = application(old, S.RETURNED)
    behalf = application(old, S.DRAFT, on_behalf=True)
    result = start_term(actor=office(), term=new)
    assert result == RolloverResult(withdrawn=3, graduated=0)
    for row in (draft, returned, behalf):
        row.refresh_from_db()
        assert row.status == S.WITHDRAWN
    events = AuditEvent.objects.filter(action="application.expired")
    assert events.count() == 3
    assert {event.data["term"] for event in events} == {new.pk}


def test_rollover_keeps_submitted_and_under_review(terms) -> None:
    old, new = terms
    submitted = application(old, S.SUBMITTED)
    reviewing = application(old, S.UNDER_REVIEW)
    start_term(actor=office(), term=new)
    submitted.refresh_from_db()
    reviewing.refresh_from_db()
    assert (submitted.status, reviewing.status) == (S.SUBMITTED, S.UNDER_REVIEW)


def test_rollover_keeps_current_term_drafts(terms) -> None:
    _, new = terms
    draft = application(new, S.DRAFT)
    start_term(actor=office(), term=new)
    draft.refresh_from_db()
    assert draft.status == S.DRAFT


def term_of(year: int, number: int) -> AcademicTerm:
    found = AcademicTerm.objects.filter(school_year_start=year, term=number).first()
    return found or AcademicTermFactory.create(school_year_start=year, term=number)


def graduating_world(max_terms: int | None) -> tuple[Award, AcademicTerm]:
    first = term_of(2025, 1)
    second = term_of(2025, 2)
    program = ProgramFactory.create(max_terms=max_terms)
    tier = BenefitTierFactory.create(program=program, effective_from=first)
    return make_scholar(program, tier, [first, second]), second


def test_rollover_graduates_at_max_terms(terms) -> None:
    _, new = terms
    award, last = graduating_world(2)
    on_hold, _ = graduating_world(2)
    Award.objects.filter(pk=on_hold.pk).update(status=Award.Status.SUSPENDED)
    short, _ = graduating_world(3)
    result = start_term(actor=office(), term=new)
    assert result.graduated == 2
    award.refresh_from_db()
    assert (award.status, award.ended_term) == (Award.Status.GRADUATED, last)
    short.refresh_from_db()
    assert short.status == Award.Status.ACTIVE
    event = AuditEvent.objects.filter(action="award.status_changed").first()
    assert event is not None
    assert event.data["to"] == "graduated" and event.data["by"] == "rollover"


def test_rollover_no_max_terms_no_graduation(terms) -> None:
    _, new = terms
    award, _ = graduating_world(None)
    assert start_term(actor=office(), term=new).graduated == 0
    award.refresh_from_db()
    assert award.status == Award.Status.ACTIVE


def test_rollover_skips_inactive_and_graduated(terms) -> None:
    _, new = terms
    ended, _ = graduating_world(1)
    Award.objects.filter(pk=ended.pk).update(status=Award.Status.INACTIVE)
    assert start_term(actor=office(), term=new).graduated == 0


def test_preview_matches_result(terms) -> None:
    old, new = terms
    application(old, S.DRAFT)
    application(old, S.SUBMITTED)
    graduating_world(1)
    preview = rollover_preview(new)
    assert preview == RolloverResult(withdrawn=1, graduated=1)
    assert start_term(actor=office(), term=new) == preview


def test_start_term_atomic(terms) -> None:
    old, new = terms
    draft = application(old, S.DRAFT)
    with mock.patch.object(services, "rollover", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            start_term(actor=office(), term=new)
    old.refresh_from_db()
    new.refresh_from_db()
    draft.refresh_from_db()
    assert (old.is_current, new.is_current) == (True, False)
    assert draft.status == S.DRAFT
    assert not AuditEvent.objects.filter(action="term.made_current").exists()


def test_rollover_idempotent(terms) -> None:
    old, new = terms
    application(old, S.DRAFT)
    graduating_world(1)
    start_term(actor=office(), term=new)
    assert rollover(actor=office(), term=new) == RolloverResult(withdrawn=0, graduated=0)


def test_expired_shows_in_history(terms) -> None:
    old, new = terms
    draft = application(old, S.RETURNED)
    start_term(actor=office(), term=new)
    assert "Withdrawn when the term ended" in [entry.what for entry in history(draft)]


def test_office_confirm_page_shows_preview(client, terms) -> None:
    old, new = terms
    application(old, S.DRAFT)
    graduating_world(1)
    client.force_login(office())
    page = html.unescape(
        client.get(reverse("office:terms-current", args=[new.pk])).content.decode()
    )
    assert "1 unfinished application will be withdrawn." in page
    assert "1 scholar will graduate." in page


def test_office_post_message(client, terms) -> None:
    old, new = terms
    application(old, S.DRAFT)
    application(old, S.RETURNED)
    client.force_login(office())
    response = client.post(reverse("office:terms-current", args=[new.pk]), follow=True)
    page = html.unescape(response.content.decode())
    assert (
        f"{new} is now the current term. Withdrew 2 unfinished applications. Graduated 0 scholars."
        in page
    )
