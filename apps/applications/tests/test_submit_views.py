from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.applications.tests.test_views import ready_file, signed_in, text
from apps.core.models import AuditEvent
from apps.programs.models import School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

SUBMITTED_TOAST = "Application submitted. We've emailed you a copy."


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


@pytest.fixture
def world():
    term = AcademicTermFactory.create(school_year_start=2026, is_current=True)
    school = SchoolFactory.create(grading_scale=School.Scale.PERCENT, type=School.Type.PRIVATE)
    program = ProgramFactory.create(
        name="Alpha", min_gwa_percent=Decimal("85.00"), applications_close_on=date(2026, 12, 1)
    )
    program.allowed_schools.add(school)
    tier = BenefitTierFactory.create(program=program, effective_from=term, code="full")
    profile = FullProfileFactory.create()
    EducationRecordFactory.create(
        profile=profile,
        school=school,
        gwa=Decimal("90.00"),
        gwa_scale=School.Scale.PERCENT,
        course="BS Nursing",
        year_level=2,
        units=18,
    )
    requirement = RequiredDocumentFactory.create(program=program, code="grades", label="Grades")
    return {
        "program": program,
        "profile": profile,
        "user": profile.user,
        "requirement": requirement,
        "term": term,
        "tier": tier,
    }


def make_application(world, *, with_document=True, **extra) -> Application:
    values = {"profile": world["profile"], "program": world["program"], "term": world["term"]}
    values.update(extra)
    application = ApplicationFactory.create(**values)
    if with_document:
        document = DocumentFactory.create(application=application, requirement=world["requirement"])
        DocumentFileFactory.create(document=document, file=ready_file(world["user"]))
    return application


def submit_url(application) -> str:
    return reverse("applications:submit", args=[application.pk])


def withdraw_url(application) -> str:
    return reverse("applications:withdraw", args=[application.pk])


def detail_url(application) -> str:
    return reverse("applications:detail", args=[application.pk])


def test_submit_success_redirect_toast_and_email_row(client, world):
    application = make_application(world)
    response = signed_in(client, world["user"]).post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 302
    assert response.url == detail_url(application)
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert application.requested_tier == world["tier"]
    assert EmailOutbox.objects.count() == 1
    assert SUBMITTED_TOAST in text(client.get(response.url))


def test_submit_without_declaration_400(client, world):
    application = make_application(world)
    response = signed_in(client, world["user"]).post(submit_url(application), {})
    assert response.status_code == 400
    assert "Confirm the declaration to submit." in text(response)
    assert "field--invalid" in response.content.decode()
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_submit_service_error_banner_400(client, world):
    application = make_application(world, with_document=False)
    response = signed_in(client, world["user"]).post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 400
    assert "banner--danger" in response.content.decode()
    assert "Upload Grades before you submit." in text(response)
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_failed_submit_rerenders_from_the_database(client, world, monkeypatch):
    """Another tab submitted while this request waited: the page shows the row as it is now."""
    from apps.applications import services
    from apps.applications.services import ALREADY_SUBMITTED

    application = make_application(world)

    def raced(*, application, **kwargs):
        Application.objects.filter(pk=application.pk).update(
            status=Application.Status.SUBMITTED, school_name="Somewhere"
        )
        raise ValidationError(ALREADY_SUBMITTED)

    monkeypatch.setattr(services, "submit_application", raced)  # views call services.<name>
    response = signed_in(client, world["user"]).post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 400
    body = text(response)
    assert ALREADY_SUBMITTED in body
    assert "Submitted</p>" in body
    assert "Submit application" not in body


def test_submit_other_student_404(client, world):
    application = make_application(world)
    other = UserFactory.create(verified=True)
    response = signed_in(client, other).post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 404
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert not AuditEvent.objects.exists()
    assert not EmailOutbox.objects.exists()


def test_submit_get_not_allowed(client, world):
    application = make_application(world)
    assert signed_in(client, world["user"]).get(submit_url(application)).status_code == 405


def test_double_submit_second_shows_sentence(client, world):
    application = make_application(world)
    signed_in(client, world["user"])
    assert client.post(submit_url(application), {"declaration": "on"}).status_code == 302
    second = client.post(submit_url(application), {"declaration": "on"})
    assert second.status_code == 400
    assert "banner--danger" in second.content.decode()
    assert "already" in text(second).lower()
    assert "Submit application" not in text(second)
    assert "I declare that" not in text(second)
    assert EmailOutbox.objects.count() == 1


def test_submit_withdrawn_shows_banner_400(client, world):
    application = make_application(world, status=Application.Status.WITHDRAWN)
    response = signed_in(client, world["user"]).post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 400
    assert "banner--danger" in response.content.decode()
    assert "Submit application" not in text(response)
    assert "I declare that" not in text(response)


def test_resubmit_returned(client, world):
    application = make_application(
        world,
        status=Application.Status.RETURNED,
        decision_reason="Fix it.",
        requested_tier=world["tier"],
    )
    signed_in(client, world["user"])
    body = text(client.get(detail_url(application)))
    assert "Resubmit application" in body
    assert "Allowance tier: " in body
    response = client.post(submit_url(application), {"declaration": "on"})
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert SUBMITTED_TOAST in text(client.get(response.url))


def test_detail_submit_card_single_tier(client, world):
    application = make_application(world)
    body = text(signed_in(client, world["user"]).get(detail_url(application)))
    assert "Submit application" in body
    assert "Allowance tier: " in body
    assert 'type="radio"' not in body
    assert "I declare that the information and documents I have given are true" in body
    assert f'action="{submit_url(application)}"' in body
    assert "Withdraw application" in body
    assert withdraw_url(application) in body


def test_detail_submit_card_several_tiers_and_choice(client, world):
    second = BenefitTierFactory.create(program=world["program"], effective_from=world["term"])
    application = make_application(world)
    signed_in(client, world["user"])
    body = client.get(detail_url(application)).content.decode()
    assert body.count('type="radio"') == 2
    missing = client.post(submit_url(application), {"declaration": "on"})
    assert missing.status_code == 400
    assert "Choose an allowance tier." in text(missing)
    response = client.post(submit_url(application), {"declaration": "on", "tier": str(second.pk)})
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.requested_tier == second


def test_detail_no_submit_card_when_submitted(client, world):
    application = make_application(world, status=Application.Status.SUBMITTED)
    body = text(signed_in(client, world["user"]).get(detail_url(application)))
    assert "Submit application" not in body
    assert "Withdraw application" in body


def test_detail_no_withdraw_link_when_approved(client, world):
    application = make_application(world, status=Application.Status.APPROVED)
    body = text(signed_in(client, world["user"]).get(detail_url(application)))
    assert "Withdraw application" not in body
    assert "Submit application" not in body


def test_withdraw_confirm_page(client, world):
    application = make_application(world)
    response = signed_in(client, world["user"]).get(withdraw_url(application))
    assert response.status_code == 200
    body = text(response)
    assert "Withdraw your Alpha application?" in body
    assert "You can apply again while applications are open." in body
    assert "btn--danger" in body
    assert "Withdraw application" in body
    assert "Cancel" in body
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_withdraw_post(client, world):
    application = make_application(world)
    response = signed_in(client, world["user"]).post(withdraw_url(application))
    assert response.status_code == 302
    assert response.url == reverse("applications:list")
    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN
    assert "Application withdrawn." in text(client.get(response.url))


def test_withdraw_under_review_error(client, world):
    application = make_application(world, status=Application.Status.UNDER_REVIEW)
    response = signed_in(client, world["user"]).post(withdraw_url(application))
    assert response.status_code == 302
    assert response.url == detail_url(application)
    assert "being reviewed and can't be withdrawn" in text(client.get(response.url))
    application.refresh_from_db()
    assert application.status == Application.Status.UNDER_REVIEW


def test_withdraw_other_student_404(client, world):
    application = make_application(world)
    other = UserFactory.create(verified=True)
    signed_in(client, other)
    assert client.get(withdraw_url(application)).status_code == 404
    assert client.post(withdraw_url(application)).status_code == 404
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert not AuditEvent.objects.exists()
