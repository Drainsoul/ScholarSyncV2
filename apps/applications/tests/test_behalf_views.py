from decimal import Decimal
from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Document
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.core.models import AuditEvent
from apps.files.models import StoredFile
from apps.files.policy import PDF
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import Program, School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
from apps.students.models import StudentProfile
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
    with django_assert_max_num_queries(13):  # +1: reports count (M11c)
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
    _profile(membership.program)
    client.force_login(membership.user)
    body = client.get(
        reverse("workspace:students", kwargs={"program": "tcu-ceaa"})
    ).content.decode()
    assert _url() in body
    profile = StudentProfile.objects.get(created_for=membership.program)
    assert f'<input type="hidden" name="profile" value="{profile.pk}">' in body
    assert "File an application" in body


# --- the filing page -----------------------------------------------------------------------


class Filing:
    """A staff member, a current term, a walk-in profile and an on-behalf draft for it."""

    def __init__(self, **application: Any) -> None:
        self.membership = _staff()
        self.program = self.membership.program
        self.actor = self.membership.user
        self.term = AcademicTermFactory.create(is_current=True)
        self.profile = _profile(self.program, first_name="Ana", last_name="Reyes")
        application.setdefault("created_by", self.actor)
        self.application = ApplicationFactory.create(
            profile=self.profile,
            program=self.program,
            term=self.term,
            on_behalf=True,
            **application,
        )

    def url(self, name: str = "behalf", **extra: Any) -> str:
        return reverse(
            f"review:{name}",
            kwargs={"program": self.program.slug, "pk": self.application.pk, **extra},
        )

    def review_url(self) -> str:
        return reverse(
            "review:detail", kwargs={"program": self.program.slug, "pk": self.application.pk}
        )


TYPED_POST = {
    "school": "",
    "school_name": "Taguig Tech",
    "school_type": School.Type.PRIVATE,
    "gwa_scale": School.Scale.PERCENT,
    "course": "BS Biology",
    "year_level": "2",
    "gwa": "88.50",
    "units": "21",
}


def _typed(filing: Filing) -> None:
    Application.objects.filter(pk=filing.application.pk).update(
        school_name="Taguig Tech",
        school_type=School.Type.PRIVATE,
        gwa_scale=School.Scale.PERCENT,
        course="BS Biology",
        year_level=2,
        gwa=Decimal("88.50"),
        units=21,
    )


def _staff_file(user: Any, **extra: Any) -> StoredFile:
    values: dict[str, Any] = {
        "uploaded_by": user,
        "status": StoredFile.Status.READY,
        "purpose": StoredFile.Purpose.DOCUMENT,
        "sniffed_type": PDF,
        "sha256": "b" * 64,
    }
    values.update(extra)
    return StoredFileFactory.create(**values)


def _messages(response: Any) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def _returned(filing: Filing) -> Document:
    """Turn the draft into a returned application with a declined document."""
    requirement = RequiredDocumentFactory.create(
        program=filing.program, code="grades", label="Grades"
    )
    Application.objects.filter(pk=filing.application.pk).update(
        status=S.RETURNED,
        school_name="Frozen College",
        school_type=School.Type.PUBLIC,
        gwa_scale=School.Scale.PERCENT,
        course="BS Frozen",
        year_level=3,
        gwa=Decimal("91.25"),
        units=18,
        decision_reason="The grades page is cut off.",
        submitted_at=timezone.now(),
        first_submitted_at=timezone.now(),
        match_snapshot={
            "evaluated_on": "2026-08-10",
            "checks": [
                {"code": "residency", "state": "unmet", "reason": "Too short"},
                {"code": "school", "state": "met", "reason": ""},
            ],
        },
    )
    document = DocumentFactory.create(
        application=filing.application,
        requirement=requirement,
        status=Document.Status.DECLINED,
        decline_reason="Page two is missing.",
    )
    DocumentFileFactory.create(document=document, file__uploaded_by=filing.actor)
    return document


def test_filing_page_draft_shows_form_rules_documents(client: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(
        min_residency_years=3, requires_registered_voter=True
    )
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="half")
    requirement = RequiredDocumentFactory.create(program=filing.program, label="Report card")
    _typed(filing)
    client.force_login(filing.actor)
    response = client.get(filing.url())
    assert response.status_code == 200
    body = response.content.decode()
    assert "Ana Reyes" in body and filing.program.name in body and str(filing.term) in body
    assert f"Filed by {filing.actor.full_name}" in body
    assert filing.url("behalf-withdraw") in body and "Withdraw" in body
    # school and grades, prefilled
    assert filing.url("behalf-academics") in body
    assert 'value="Taguig Tech"' in body and 'value="88.50"' in body
    # the live rules
    assert "Living in Taguig for at least 3 years." in body
    assert "Staff can file even when a rule isn't met. Say why below." in body
    # documents, with the uploader posting to behalf-document
    assert "Report card" in body
    assert filing.url("behalf-document", requirement=requirement.pk) in body
    assert "data-upload" in body
    # submit: tier radios and the override reason
    assert filing.url("behalf-submit") in body
    assert 'name="tier"' in body and 'type="radio"' in body
    assert 'name="override_reason"' in body
    assert "Resubmit" not in body


def test_filing_page_eligible_draft_has_no_override_prompt(client: Any) -> None:
    filing = Filing()
    _typed(filing)
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "Say why below." not in body


def test_filing_page_returned_shows_frozen_academics_and_resubmit(client: Any) -> None:
    filing = Filing()
    _returned(filing)
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="half")
    client.force_login(filing.actor)
    response = client.get(filing.url())
    assert response.status_code == 200
    body = response.content.decode()
    assert "Frozen College" in body and "BS Frozen" in body and "91.25" in body
    assert filing.url("behalf-academics") not in body
    assert 'name="school_name"' not in body
    assert "Resubmit" in body
    assert 'name="tier"' not in body and 'name="override_reason"' not in body
    # the frozen snapshot, as the review screen shows it
    assert "Meets the residency requirement" in body and "Too short" in body
    assert "Say why below." not in body


def test_filing_page_returned_shows_return_and_decline_reasons(client: Any) -> None:
    filing = Filing()
    document = _returned(filing)
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "Returned for fixes" in body
    assert "The grades page is cut off." in body
    assert body.index("Page two is missing.") > body.index(f'id="doc-{document.requirement_id}"')


def test_filing_page_filed_by_fallback(client: Any) -> None:
    filing = Filing(created_by=None)
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "Filed by staff" in body


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.APPROVED, S.WITHDRAWN])
def test_filing_page_redirects_when_submitted(client: Any, status: str) -> None:
    filing = Filing()
    Application.objects.filter(pk=filing.application.pk).update(
        status=status, school_name="Frozen College", submitted_at=timezone.now()
    )
    client.force_login(filing.actor)
    response = client.get(filing.url())
    assert response.status_code == 302
    assert response.url == filing.review_url()


def test_filing_page_404_for_student_application_and_other_program(client: Any) -> None:
    filing = Filing()
    student = ApplicationFactory.create(program=filing.program)
    foreign = ApplicationFactory.create(on_behalf=True)
    client.force_login(filing.actor)
    for pk in (student.pk, foreign.pk):
        url = reverse("review:behalf", kwargs={"program": filing.program.slug, "pk": pk})
        assert client.get(url).status_code == 404


def test_academics_post_saves_and_redirects(client: Any) -> None:
    filing = Filing()
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-academics"), TYPED_POST)
    assert response.status_code == 302 and response.url == filing.url()
    filing.application.refresh_from_db()
    assert filing.application.school_name == "Taguig Tech"
    assert filing.application.gwa == Decimal("88.50")
    assert filing.application.units == 21
    assert AuditEvent.objects.filter(action="application.academics_set").count() == 1


def test_academics_post_invalid_rerenders_400(client: Any) -> None:
    filing = Filing()
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-academics"), {**TYPED_POST, "school_name": ""})
    assert response.status_code == 400
    body = response.content.decode()
    assert "Choose the student&#x27;s school or type its name." in body
    assert 'value="BS Biology"' in body  # the bound form keeps what was typed
    filing.application.refresh_from_db()
    assert filing.application.course == ""
    assert not AuditEvent.objects.exclude(action="user.signed_in").exists()


def test_academics_post_after_submit_redirects_to_review(client: Any) -> None:
    filing = Filing()
    Application.objects.filter(pk=filing.application.pk).update(
        status=S.SUBMITTED, school_name="Frozen College", submitted_at=timezone.now()
    )
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-academics"), TYPED_POST)
    assert response.status_code == 302 and response.url == filing.review_url()
    assert "The school and grades are frozen once the application is submitted." in _messages(
        response
    )


def test_document_post_saves_and_redirects(client: Any) -> None:
    filing = Filing()
    requirement = RequiredDocumentFactory.create(program=filing.program, label="Report card")
    file = _staff_file(filing.actor)
    client.force_login(filing.actor)
    response = client.post(
        filing.url("behalf-document", requirement=requirement.pk), {"file": str(file.pk)}
    )
    assert response.status_code == 302
    assert response.url == f"{filing.url()}#doc-{requirement.pk}"
    assert Document.objects.filter(application=filing.application).count() == 1


def test_document_post_error_on_its_row(client: Any) -> None:
    filing = Filing()
    first = RequiredDocumentFactory.create(program=filing.program, label="Report card")
    second = RequiredDocumentFactory.create(program=filing.program, label="Barangay ID")
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-document", requirement=second.pk), {"file": ""})
    assert response.status_code == 400
    body = response.content.decode()
    error = body.index("Upload a file first.")
    assert body.index(f'id="doc-{first.pk}"') < body.index(f'id="doc-{second.pk}"') < error
    assert f'href="#doc-{second.pk}"' in body  # the banner points at the row
    assert not Document.objects.exists()


def test_document_post_other_programs_requirement_404(client: Any) -> None:
    filing = Filing()
    foreign = RequiredDocumentFactory.create(program=ProgramFactory.create(slug="lani"))
    file = _staff_file(filing.actor)
    client.force_login(filing.actor)
    response = client.post(
        filing.url("behalf-document", requirement=foreign.pk), {"file": str(file.pk)}
    )
    assert response.status_code == 404
    assert not Document.objects.exists()


def test_submit_post_override_missing_reason_rerenders_with_sentence(client: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(
        min_residency_years=3, requires_registered_voter=True
    )
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    _typed(filing)
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-submit"), {"override_reason": "  "})
    assert response.status_code == 400
    body = response.content.decode()
    assert "This student doesn&#x27;t meet every rule. Say why you&#x27;re filing anyway." in body
    filing.application.refresh_from_db()
    assert filing.application.status == S.DRAFT


def test_submit_post_reason_too_long_is_refused(client: Any) -> None:
    filing = Filing()
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    _typed(filing)
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-submit"), {"override_reason": "x" * 1001})
    assert response.status_code == 400
    filing.application.refresh_from_db()
    assert filing.application.status == S.DRAFT


def test_submit_post_success_redirects_to_review(client: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(min_residency_years=3)
    full = BenefitTierFactory.create(
        program=filing.program, effective_from=filing.term, code="full"
    )
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="half")
    _typed(filing)
    client.force_login(filing.actor)
    response = client.post(
        filing.url("behalf-submit"), {"tier": str(full.pk), "override_reason": "Walk-in"}
    )
    assert response.status_code == 302 and response.url == filing.review_url()
    assert "Submitted Ana Reyes's application." in _messages(response)
    filing.application.refresh_from_db()
    assert filing.application.status == S.SUBMITTED
    assert filing.application.requested_tier == full
    assert filing.application.override_reason == "Walk-in"


def test_submit_post_needs_tier_choice(client: Any) -> None:
    filing = Filing()
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="half")
    _typed(filing)
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-submit"), {})
    assert response.status_code == 400
    filing.application.refresh_from_db()
    assert filing.application.status == S.DRAFT


def test_resubmit_post_returned(client: Any) -> None:
    filing = Filing()
    document = _returned(filing)
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="full")
    BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code="half")
    client.force_login(filing.actor)
    response = client.post(filing.url("behalf-submit"), {})  # the declined file is still there
    assert response.status_code == 400
    assert "Upload Grades before you submit." in response.content.decode()
    file = _staff_file(filing.actor, sha256="c" * 64)
    client.post(
        filing.url("behalf-document", requirement=document.requirement_id), {"file": str(file.pk)}
    )
    response = client.post(filing.url("behalf-submit"), {})
    assert response.status_code == 302 and response.url == filing.review_url()
    filing.application.refresh_from_db()
    assert filing.application.status == S.SUBMITTED


def test_filing_page_has_no_student_fix_links(client: Any) -> None:
    filing = Filing()  # no school yet: the school check is missing, with a profile fix link
    Program.objects.filter(pk=filing.program.pk).update(min_residency_years=3)
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "Say why below." in body
    assert "/me/" not in body


def test_filing_page_query_budget(client: Any, django_assert_max_num_queries: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(min_residency_years=3)
    for code in ("full", "half", "third"):
        BenefitTierFactory.create(program=filing.program, effective_from=filing.term, code=code)
    _typed(filing)
    for _ in range(5):
        requirement = RequiredDocumentFactory.create(program=filing.program)
        document = DocumentFactory.create(application=filing.application, requirement=requirement)
        DocumentFileFactory.create(document=document, file__uploaded_by=filing.actor)
    client.force_login(filing.actor)
    with django_assert_max_num_queries(25):
        response = client.get(filing.url())
    assert response.status_code == 200
    assert len(response.context["cards"]) == 5


# --- follow-up fixes -----------------------------------------------------------------------


def test_filing_page_uses_staff_wording_for_missing_data(client: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(
        min_residency_years=3, requires_registered_voter=True, min_units=15
    )
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "your profile" not in body.lower()
    assert "Enter this in School and grades above." in body
    assert "Not on the student&#x27;s profile. Override with a reason, or ask the student." in body


def test_filing_page_third_person_for_unmet_gwa(client: Any) -> None:
    filing = Filing()
    Program.objects.filter(pk=filing.program.pk).update(min_gwa_percent=Decimal("90.00"))
    _typed(filing)
    client.force_login(filing.actor)
    body = client.get(filing.url()).content.decode()
    assert "Your GWA" not in body
    assert "The student&#x27;s GWA of 88.50 doesn&#x27;t meet" in body


def test_review_screen_staff_wording_for_on_behalf_snapshot(client: Any) -> None:
    filing = Filing()
    Application.objects.filter(pk=filing.application.pk).update(
        status=S.SUBMITTED,
        school_name="Frozen College",
        submitted_at=timezone.now(),
        first_submitted_at=timezone.now(),
        match_snapshot={
            "evaluated_on": "2026-08-10",
            "checks": [
                {"code": "units", "state": "missing", "reason": "Add your units this term."},
                {"code": "voter", "state": "missing", "reason": "Say whether you are a voter."},
            ],
        },
    )
    client.force_login(filing.actor)
    body = client.get(filing.review_url()).content.decode()
    assert "Not entered when the application was filed." in body
    assert "Not on the student&#x27;s profile." in body
    assert "Add your units" not in body


def test_review_screen_withdrawn_and_history_wording_on_behalf(client: Any) -> None:
    from apps.core import audit

    filing = Filing()
    Application.objects.filter(pk=filing.application.pk).update(
        status=S.WITHDRAWN,
        school_name="Frozen College",
        submitted_at=timezone.now(),
        first_submitted_at=timezone.now(),
    )
    audit.record(actor=filing.actor, action="application.returned", target=filing.application)
    client.force_login(filing.actor)
    body = client.get(filing.review_url()).content.decode()
    assert "Withdrawn by staff" in body and "Withdrawn by the student" not in body
    assert "Returned for fixes" in body and "Returned to the student" not in body


def test_bookmarked_filing_url_for_never_submitted_withdrawn_goes_to_new(client: Any) -> None:
    filing = Filing()
    Application.objects.filter(pk=filing.application.pk).update(status=S.WITHDRAWN)
    client.force_login(filing.actor)
    response = client.get(filing.url())
    assert response.status_code == 302 and response.url == _url()


# --- find a student by account email (rev 33, §18 Q16) ---------------------------------------

LOOKUP_EMAIL = "mara.selfsigned@scholarsync.test"


def _find_url(slug: str = "tcu-ceaa") -> str:
    return reverse("review:behalf-find", kwargs={"program": slug})


def _self_registered(**user: Any) -> Any:
    account = UserFactory.create(email=LOOKUP_EMAIL, verified=True, **user)
    return ProfileFactory.create(user=account, created_for=None, first_name="Mara", last_name="Sy")


def test_new_page_has_the_lookup_form(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    body = client.get(_url()).content.decode()
    assert "Find a student by account email" in body
    assert f'action="{_find_url()}"' in body
    assert 'method="post" action="' + _find_url() in body


def test_find_match_shows_name_and_file_button(client: Any) -> None:
    membership = _staff()
    profile = _self_registered()
    client.force_login(membership.user)
    response = client.post(_find_url(), {"email": "Mara.SelfSigned@ScholarSync.test"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "Found <strong>Mara Sy</strong>." in body
    assert 'File an application<span class="visually-hidden"> for Mara Sy' in body
    assert f'name="profile" value="{profile.pk}"' in body
    assert response.context["found"].profile == profile
    assert "No student account uses that email." not in body


@pytest.mark.parametrize("kind", ["unknown", "inactive", "staff", "no-profile"])
def test_find_no_match_says_so(client: Any, kind: str) -> None:
    membership = _staff()
    if kind == "inactive":
        _self_registered(is_active=False)
    elif kind == "staff":
        UserFactory.create(email=LOOKUP_EMAIL, verified=True, role=User.Role.STAFF)
    elif kind == "no-profile":
        UserFactory.create(email=LOOKUP_EMAIL, verified=True)
    client.force_login(membership.user)
    response = client.post(_find_url(), {"email": LOOKUP_EMAIL})
    assert response.status_code == 200
    assert "No student account uses that email." in response.content.decode()
    assert response.context["found"] is None


@pytest.mark.parametrize("value", ["", "not-an-email"])
def test_find_invalid_email_is_a_form_error_and_no_lookup(client: Any, value: str) -> None:
    membership = _staff()
    client.force_login(membership.user)
    response = client.post(_find_url(), {"email": value})
    assert response.status_code == 400
    assert response.context["lookup_form"].errors
    assert not AuditEvent.objects.filter(action="application.email_lookup").exists()


def test_find_limit_refuses_without_looking(client: Any) -> None:
    membership = _staff()
    _self_registered()
    client.force_login(membership.user)
    for index in range(30):
        client.post(_find_url(), {"email": f"nobody{index}@scholarsync.test"})
    response = client.post(_find_url(), {"email": LOOKUP_EMAIL})
    assert response.status_code == 429
    body = response.content.decode()
    assert "You&#x27;ve looked up 30 addresses today. Try again tomorrow." in body
    assert response.context["found"] is None
    assert AuditEvent.objects.filter(action="application.email_lookup").count() == 30


def test_find_never_puts_the_address_in_audit_or_url(client: Any) -> None:
    membership = _staff()
    _self_registered()
    client.force_login(membership.user)
    response = client.post(_find_url(), {"email": LOOKUP_EMAIL})
    assert LOOKUP_EMAIL not in response.wsgi_request.get_full_path()
    assert "scholarsync.test" not in str(list(AuditEvent.objects.values())).lower()


def test_find_then_file_starts_the_draft(client: Any) -> None:
    membership = _staff()
    AcademicTermFactory.create(is_current=True)
    profile = _self_registered()
    client.force_login(membership.user)
    found = client.post(_find_url(), {"email": LOOKUP_EMAIL}).context["found"]
    response = client.post(_url(), {"profile": profile.pk, "lookup": found.token})
    application = Application.objects.get(profile=profile)
    assert application.on_behalf and application.program == membership.program
    assert response.status_code == 302
    assert response.url == reverse(
        "review:behalf", kwargs={"program": "tcu-ceaa", "pk": application.pk}
    )
    page = client.get(response.url)
    assert page.status_code == 200
    assert "Mara Sy" in page.content.decode()


def test_file_for_self_registered_without_lookup_404(client: Any) -> None:
    membership = _staff()
    AcademicTermFactory.create(is_current=True)
    profile = _self_registered()
    client.force_login(membership.user)
    assert client.post(_url(), {"profile": profile.pk}).status_code == 404
    assert client.post(_url(), {"profile": profile.pk, "lookup": "x" * 5000}).status_code == 404
    assert Application.objects.count() == 0


def test_other_programs_staff_404_on_found_students_application(client: Any) -> None:
    membership = _staff()
    AcademicTermFactory.create(is_current=True)
    profile = _self_registered()
    client.force_login(membership.user)
    found = client.post(_find_url(), {"email": LOOKUP_EMAIL}).context["found"]
    client.post(_url(), {"profile": profile.pk, "lookup": found.token})
    application = Application.objects.get(profile=profile)
    other = _staff("lani")
    client.force_login(other.user)
    lani = {"program": "lani", "pk": application.pk}
    assert client.get(reverse("review:behalf", kwargs=lani)).status_code == 404
    assert client.post(reverse("review:behalf-withdraw", kwargs=lani)).status_code == 404
    # The other program's lookup token never starts a draft here either.
    assert (
        client.post(_url("lani"), {"profile": profile.pk, "lookup": found.token}).status_code == 404
    )


def test_find_query_budget(client: Any, django_assert_max_num_queries: Any) -> None:
    membership = _staff()
    program = membership.program
    AcademicTermFactory.create(is_current=True)
    for _ in range(30):
        _profile(program)
    _self_registered()
    client.force_login(membership.user)
    with django_assert_max_num_queries(20):  # the page (13) + lock, count, match, audit
        response = client.post(_find_url(), {"email": LOOKUP_EMAIL})
    assert response.status_code == 200
    assert response.context["found"] is not None
