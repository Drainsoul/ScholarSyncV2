"""Staff review of renewals (M9)."""

import html
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications import review
from apps.applications.models import Application, Document
from apps.applications.review_selectors import QueueFilters, parse_queue_filters, queue
from apps.applications.tests.factories import DocumentFactory, DocumentFileFactory
from apps.awards.models import Award, ScholarTerm
from apps.awards.services import AWARD_ENDED, AWARD_ON_HOLD, TERM_EXISTS
from apps.awards.tests.factories import RenewalFactory
from apps.awards.tests.scholars import add_record, make_scholar
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db


def staff_of(program: Program) -> User:
    return MembershipFactory.create(program=program).user


def setup_terms() -> tuple[AcademicTerm, AcademicTerm]:
    previous = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    return previous, current


def renewal_under_review(
    *, merit: bool | None = None
) -> tuple[Application, Award, AcademicTerm, BenefitTier]:
    previous, current = setup_terms()
    program = ProgramFactory.create()
    tier = BenefitTierFactory.create(program=program, effective_from=previous, code="standard")
    award = make_scholar(program, tier, [previous])
    now = timezone.now()
    application = RenewalFactory.create(
        award=award,
        term=current,
        status=Application.Status.UNDER_REVIEW,
        submitted_at=now,
        first_submitted_at=now,
        requested_tier=tier,
        school_name="Renewal College",
        school_type="private",
        gwa=Decimal("91.00"),
        gwa_scale="percent",
        units=21,
        year_level=3,
        match_snapshot={"merit_likely": merit, "checks": []},
    )
    document = DocumentFactory.create(application=application, status=Document.Status.APPROVED)
    DocumentFileFactory.create(document=document)
    return application, award, current, tier


def approve(application: Application, tier: BenefitTier | None = None) -> object:
    return review.approve_application(
        actor=staff_of(application.program),
        program=application.program,
        application=application,
        tier=tier,
    )


def test_approve_renewal_adds_term() -> None:
    application, award, current, tier = renewal_under_review(merit=True)
    result = approve(application)
    assert isinstance(result, ScholarTerm)
    assert Award.objects.count() == 1
    record = ScholarTerm.objects.get(award=award, term=current)
    assert (record.school_name, record.gwa, record.units, record.year_level) == (
        "Renewal College",
        Decimal("91.00"),
        21,
        3,
    )
    assert record.merit is True
    assert record.compliance == ScholarTerm.Compliance.COMPLETE
    assert record.tier == tier
    application.refresh_from_db()
    assert application.status == Application.Status.APPROVED
    created = AuditEvent.objects.get(action="scholar_term.created")
    assert created.data == {
        "award": award.pk,
        "term": current.pk,
        "source": "renewal",
        "tier": "standard",
    }
    approved = AuditEvent.objects.get(action="application.approved")
    assert approved.data["kind"] == "renewal"


def assert_refused(application: Application, message: str) -> None:
    before = AuditEvent.objects.count()
    with pytest.raises(ValidationError) as caught:
        approve(application)
    assert caught.value.messages == [message]
    application.refresh_from_db()
    assert application.status == Application.Status.UNDER_REVIEW
    assert AuditEvent.objects.count() == before
    assert not EmailOutbox.objects.exists()


def test_approve_renewal_award_on_hold() -> None:
    application, award, _, _ = renewal_under_review()
    Award.objects.filter(pk=award.pk).update(status=Award.Status.SUSPENDED)
    assert_refused(application, AWARD_ON_HOLD)


@pytest.mark.parametrize("status", [Award.Status.INACTIVE, Award.Status.GRADUATED])
def test_approve_renewal_award_ended(status: str) -> None:
    application, award, _, _ = renewal_under_review()
    Award.objects.filter(pk=award.pk).update(status=status)
    assert_refused(application, AWARD_ENDED)


def test_approve_renewal_term_exists() -> None:
    application, award, current, _ = renewal_under_review()
    add_record(award, current)
    assert_refused(application, TERM_EXISTS.format(term=current))


def test_approve_after_reprice_uses_same_code_for_renewal() -> None:
    application, award, current, _ = renewal_under_review()
    repriced = BenefitTierFactory.create(
        program=application.program, effective_from=current, code="standard"
    )
    approve(application)
    award.refresh_from_db()
    assert award.tier == repriced
    assert ScholarTerm.objects.get(award=award, term=current).tier == repriced


def test_approve_after_reprice_uses_same_code_for_new_application() -> None:
    previous, current = setup_terms()
    program = ProgramFactory.create()
    old = BenefitTierFactory.create(program=program, effective_from=previous, code="full")
    now = timezone.now()
    application = Application.objects.create(
        profile=make_scholar(program, old, [previous], status=Award.Status.INACTIVE).profile,
        program=program,
        term=current,
        status=Application.Status.UNDER_REVIEW,
        submitted_at=now,
        first_submitted_at=now,
        requested_tier=old,
        school_name="College",
    )
    document = DocumentFactory.create(application=application, status=Document.Status.APPROVED)
    DocumentFileFactory.create(document=document)
    repriced = BenefitTierFactory.create(program=program, effective_from=current, code="full")
    award = approve(application)
    assert isinstance(award, Award)
    assert award.tier == repriced


def test_bulk_approve_renewal_after_reprice() -> None:
    application, award, current, _ = renewal_under_review()
    BenefitTierFactory.create(program=application.program, effective_from=current, code="standard")
    result = review.bulk_action(
        actor=staff_of(application.program),
        program=application.program,
        action="approve",
        ids=[application.pk],
    )
    assert (result.done, result.skipped) == (1, [])
    assert ScholarTerm.objects.filter(award=award, term=current).exists()


def test_renewal_decided_email_sent() -> None:
    application, _, _, _ = renewal_under_review()
    approve(application)
    email = EmailOutbox.objects.get()
    assert email.kind == "application_decided"
    assert email.context["outcome"] == "approved"


def test_queue_kind_filter() -> None:
    application, _, _, _ = renewal_under_review()
    program = application.program
    now = timezone.now()
    fresh = Application.objects.create(
        profile=make_scholar(
            program,
            BenefitTierFactory.create(program=program),
            [application.term],
            status=Award.Status.INACTIVE,
        ).profile,
        program=program,
        term=application.term,
        status=Application.Status.SUBMITTED,
        submitted_at=now,
        first_submitted_at=now,
        school_name="College",
    )
    assert list(queue(program, QueueFilters(kind="renewal"))) == [application]
    assert list(queue(program, QueueFilters(kind="new"))) == [fresh]
    assert set(queue(program, QueueFilters())) == {application, fresh}


def test_queue_unknown_kind_falls_back() -> None:
    from django.http import QueryDict

    assert parse_queue_filters(QueryDict("kind=bogus")).kind == ""
    assert parse_queue_filters(QueryDict("kind=renewal")).kind == "renewal"


def test_review_screen_renewal_banner(client) -> None:
    application, award, current, _ = renewal_under_review()
    client.force_login(staff_of(application.program))
    url = reverse(
        "review:detail", kwargs={"program": application.program.slug, "pk": application.pk}
    )
    body = html.unescape(client.get(url).content.decode())
    assert f"Renewal for {current}. Scholar since {award.started_term}." in body
    assert f"Last term ({award.started_term}): GWA 88.00, 18 units." in body
    record = reverse(
        "scholars:detail", kwargs={"program": application.program.slug, "pk": award.pk}
    )
    assert record in body


def test_review_screen_renewal_checks_labelled(client) -> None:
    application, _, _, _ = renewal_under_review()
    application.match_snapshot = {
        "checks": [
            {"code": "renewal_gwa", "state": "met", "reason": ""},
            {"code": "renewal_units", "state": "met", "reason": ""},
        ]
    }
    application.save(update_fields=["match_snapshot"])
    client.force_login(staff_of(application.program))
    url = reverse(
        "review:detail", kwargs={"program": application.program.slug, "pk": application.pk}
    )
    body = html.unescape(client.get(url).content.decode())
    assert "Meets the renewal grade requirement" in body
    assert "Carries enough units to renew" in body


def test_queue_page_shows_kind_column(client) -> None:
    application, _, _, _ = renewal_under_review()
    client.force_login(staff_of(application.program))
    url = reverse("review:queue", kwargs={"program": application.program.slug})
    body = html.unescape(client.get(url).content.decode())
    assert ">Kind<" in body
    assert "Renewal" in body


def test_decide_view_renewal_message(client) -> None:
    application, _, current, tier = renewal_under_review()
    client.force_login(staff_of(application.program))
    url = reverse(
        "review:decide", kwargs={"program": application.program.slug, "pk": application.pk}
    )
    response = client.post(url, {"decision": "approve", "tier": tier.pk, "reason": ""}, follow=True)
    body = html.unescape(response.content.decode())
    name = application.profile.full_name
    assert f"Application approved. {name}'s scholarship is renewed for {current}." in body


def test_decision_form_preselects_same_code_after_reprice() -> None:
    from apps.applications.staff_forms import DecisionForm

    application, _, current, _ = renewal_under_review()
    repriced = BenefitTierFactory.create(
        program=application.program, effective_from=current, code="standard"
    )
    form = DecisionForm(program=application.program, application=application)
    assert form.fields["tier"].initial == repriced.pk
