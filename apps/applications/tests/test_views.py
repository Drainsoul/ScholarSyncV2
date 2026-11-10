import html
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Document, DocumentFile
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.files.models import StoredFile
from apps.files.policy import PDF, PNG
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import EducationRecordFactory, FullProfileFactory

pytestmark = pytest.mark.django_db

LIST_BUDGET = 6
DETAIL_BUDGET = 14


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


@pytest.fixture
def term():
    return AcademicTermFactory.create(school_year_start=2026, is_current=True)


@pytest.fixture
def world(term):
    school = SchoolFactory.create(grading_scale=School.Scale.PERCENT, type=School.Type.PRIVATE)
    program = ProgramFactory.create(
        name="Alpha", min_gwa_percent=Decimal("85.00"), applications_close_on=date(2026, 12, 1)
    )
    program.allowed_schools.add(school)
    BenefitTierFactory.create(program=program, effective_from=term, code="full")
    profile = FullProfileFactory.create()
    education = EducationRecordFactory.create(
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
        "education": education,
        "requirement": requirement,
        "term": term,
    }


def text(response) -> str:
    return html.unescape(response.content.decode())


def draft(world, **extra) -> Application:
    values = {"profile": world["profile"], "program": world["program"], "term": world["term"]}
    values.update(extra)
    return ApplicationFactory.create(**values)


def ready_file(user, **extra) -> StoredFile:
    values = {
        "uploaded_by": user,
        "status": StoredFile.Status.READY,
        "purpose": StoredFile.Purpose.DOCUMENT,
        "sniffed_type": PDF,
        "sha256": "c" * 64,
        "original_name": "my-grades.pdf",
    }
    values.update(extra)
    return StoredFileFactory.create(**values)


def signed_in(client, user):
    client.force_login(user)
    return client


def detail_body(client, world, application) -> str:
    response = signed_in(client, world["user"]).get(
        reverse("applications:detail", args=[application.pk])
    )
    return text(response)


# --- list -----------------------------------------------------------------------------------


def test_list_rows_and_status_text(client, world):
    submitted = draft(
        world,
        status=Application.Status.SUBMITTED,
        submitted_at=datetime(2026, 10, 10, 9, 0, tzinfo=ZoneInfo("Asia/Manila")),
    )
    ApplicationFactory.create(
        profile=world["profile"], program=ProgramFactory.create(name="Beta"), term=world["term"]
    )
    ApplicationFactory.create()  # someone else's
    body = text(signed_in(client, world["user"]).get(reverse("applications:list")))
    assert "Alpha" in body and "Beta" in body
    assert "status--info" in body and "Submitted" in body
    assert "status--warning" in body and "Draft" in body
    assert "Not submitted" in body
    assert "10 Oct 2026" in body
    assert f'href="{reverse("applications:detail", args=[submitted.pk])}"' in body
    assert body.count("<tr>") == 3  # header + two rows


def test_list_empty_state(client, world):
    body = text(signed_in(client, world["user"]).get(reverse("applications:list")))
    assert "No applications yet." in body
    assert "Find scholarships" in body
    assert reverse("matching:match") in body


def test_list_query_budget(client, world, django_assert_max_num_queries):
    draft(world)
    ApplicationFactory.create(
        profile=world["profile"], program=ProgramFactory.create(), term=world["term"]
    )
    signed_in(client, world["user"])
    with django_assert_max_num_queries(LIST_BUDGET):
        assert client.get(reverse("applications:list")).status_code == 200


# --- new ------------------------------------------------------------------------------------


def test_new_get_writes_nothing(client, world):
    user = UserFactory.create(verified=True)
    url = reverse("applications:new", args=[world["program"].slug])
    assert signed_in(client, user).get(url).status_code == 200
    assert StudentProfile.objects.filter(user=user).count() == 0
    assert signed_in(client, world["user"]).get(url).status_code == 200
    assert Application.objects.count() == 0


def test_new_get_unknown_or_inactive_slug_404(client, world):
    signed_in(client, world["user"])
    assert client.get(reverse("applications:new", args=["nope"])).status_code == 404
    inactive = ProgramFactory.create(is_active=False)
    assert client.get(reverse("applications:new", args=[inactive.slug])).status_code == 404
    assert client.post(reverse("applications:new", args=["nope"])).status_code == 404


def test_new_get_page_content(client, world):
    response = signed_in(client, world["user"]).get(
        reverse("applications:new", args=[world["program"].slug])
    )
    body = text(response)
    assert "<h1>Apply to Alpha</h1>" in body
    assert "Applications close on 1 Dec 2026" in body
    assert "checklist" in body
    assert "Start application" in body


def test_new_get_no_closing_date(client, world):
    world["program"].applications_close_on = None
    world["program"].save()
    url = reverse("applications:new", args=[world["program"].slug])
    assert "No closing date" in text(signed_in(client, world["user"]).get(url))


def test_new_get_redirects_to_open_application(client, world):
    application = draft(world)
    response = signed_in(client, world["user"]).get(
        reverse("applications:new", args=[world["program"].slug])
    )
    assert response.status_code == 302
    assert response.url == reverse("applications:detail", args=[application.pk])


def test_new_get_ineligible_has_no_start_button(client, world):
    world["education"].delete()
    url = reverse("applications:new", args=[world["program"].slug])
    body = text(signed_in(client, world["user"]).get(url))
    assert "Start application" not in body
    assert "is-missing" in body


def test_new_post_creates_and_redirects(client, world):
    response = signed_in(client, world["user"]).post(
        reverse("applications:new", args=[world["program"].slug])
    )
    application = Application.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("applications:detail", args=[application.pk])
    assert application.status == Application.Status.DRAFT
    assert "Application started." in text(client.get(response.url))


def test_new_post_twice_same_draft(client, world):
    url = reverse("applications:new", args=[world["program"].slug])
    signed_in(client, world["user"])
    first = client.post(url)
    second = client.post(url)
    assert Application.objects.count() == 1
    assert first.url == second.url


def test_new_post_ineligible_rerenders_400_with_sentence(client, world):
    world["education"].delete()
    response = signed_in(client, world["user"]).post(
        reverse("applications:new", args=[world["program"].slug])
    )
    assert response.status_code == 400
    assert "banner--danger" in response.content.decode()
    assert Application.objects.count() == 0


# --- detail ---------------------------------------------------------------------------------


def test_detail_other_student_404(client, world):
    application = draft(world)
    other = UserFactory.create(verified=True)
    response = signed_in(client, other).get(reverse("applications:detail", args=[application.pk]))
    assert response.status_code == 404


def test_detail_header_and_documents(client, world):
    application = draft(world)
    RequiredDocumentFactory.create(
        program=world["program"], code="id", label="Valid ID", help_text="Front and back."
    )
    document = DocumentFactory.create(application=application, requirement=world["requirement"])
    DocumentFileFactory.create(document=document, file=ready_file(world["user"]))
    body = detail_body(client, world, application)
    assert "<h1>Alpha application</h1>" in body
    assert f"{world['term']} · Draft" in body
    assert "1 of 2 required documents uploaded" in body
    assert "my-grades.pdf" in body
    assert "Waiting for review" in body
    assert "Front and back." in body
    assert f'id="doc-{world["requirement"].pk}"' in body
    assert "Save document" in body
    assert "Submit application" in body
    assert "Withdraw application" in body


def test_detail_declined_document_shows_reason(client, world):
    application = draft(world)
    document = DocumentFactory.create(
        application=application,
        requirement=world["requirement"],
        status=Document.Status.DECLINED,
        decline_reason="Blurry scan.",
    )
    DocumentFileFactory.create(document=document, file=ready_file(world["user"]))
    body = detail_body(client, world, application)
    assert "Declined: Blurry scan." in body
    assert "status--danger" in body


def test_detail_approved_document_has_no_form(client, world):
    application = draft(world, status=Application.Status.RETURNED, decision_reason="Fix it.")
    document = DocumentFactory.create(
        application=application,
        requirement=world["requirement"],
        status=Document.Status.APPROVED,
    )
    DocumentFileFactory.create(document=document, file=ready_file(world["user"]))
    body = detail_body(client, world, application)
    assert "status--success" in body
    assert "Save document" not in body


def test_detail_shows_live_education_for_draft_and_snapshot_after_submit(client, world):
    application = draft(world)
    assert "BS Nursing" in detail_body(client, world, application)
    world["education"].course = "BS Biology"
    world["education"].save()
    body = detail_body(client, world, application)
    assert "BS Biology" in body
    assert "Edit in your profile" in body
    Application.objects.filter(pk=application.pk).update(
        status=Application.Status.SUBMITTED,
        school=world["education"].school,
        course="BS Nursing",
        gwa=Decimal("91.50"),
        year_level=2,
    )
    body = detail_body(client, world, application)
    assert "BS Nursing" in body
    assert "BS Biology" not in body
    assert "91.5" in body
    assert "Edit in your profile" not in body


def test_detail_returned_banner(client, world):
    application = draft(world, status=Application.Status.RETURNED, decision_reason="Add your ID.")
    body = detail_body(client, world, application)
    assert "Staff returned this application: Add your ID." in body
    assert "banner--warning" in body


def test_detail_query_budget(client, world, django_assert_max_num_queries):
    application = draft(world)
    for index in range(3):
        requirement = RequiredDocumentFactory.create(program=world["program"], code=f"r{index}")
        document = DocumentFactory.create(application=application, requirement=requirement)
        DocumentFileFactory.create(document=document, file=ready_file(world["user"]))
    signed_in(client, world["user"])
    with django_assert_max_num_queries(DETAIL_BUDGET):
        assert client.get(reverse("applications:detail", args=[application.pk])).status_code == 200


def test_no_upload_form_when_submitted(client, world):
    application = draft(world, status=Application.Status.SUBMITTED)
    body = detail_body(client, world, application)
    assert "Save document" not in body
    assert 'data-upload-purpose="document"' not in body


# --- document -------------------------------------------------------------------------------


def doc_url(application, requirement):
    return reverse("applications:document", args=[application.pk, requirement.pk])


def test_document_post_saves_and_redirects(client, world):
    application = draft(world)
    file = ready_file(world["user"])
    response = signed_in(client, world["user"]).post(
        doc_url(application, world["requirement"]), {"file": str(file.pk)}
    )
    assert response.status_code == 302
    assert response.url == (
        reverse("applications:detail", args=[application.pk]) + f"#doc-{world['requirement'].pk}"
    )
    assert DocumentFile.objects.filter(file=file, is_current=True).exists()
    assert "Document saved." in text(client.get(response.url))


def test_document_post_bad_file_shows_row_error_400(client, world):
    world["requirement"].accepted_types = [PDF]
    world["requirement"].save()
    other = RequiredDocumentFactory.create(program=world["program"], code="id", label="Valid ID")
    application = draft(world)
    wrong = ready_file(world["user"], sniffed_type=PNG)
    response = signed_in(client, world["user"]).post(
        doc_url(application, world["requirement"]), {"file": str(wrong.pk)}
    )
    assert response.status_code == 400
    body = response.content.decode()
    assert body.count("field--invalid") == 1
    assert body.count("field__error") == 1
    assert "This document must be a" in text(response)
    first = body.index(f'id="doc-{world["requirement"].pk}"')
    second = body.index(f'id="doc-{other.pk}"')
    assert first < body.index("field--invalid") < second
    assert not Document.objects.exists()


def test_document_post_error_has_a_banner_linking_to_the_row(client, world):
    """Keyboard and screen-reader users land on the alert, which points at the row."""
    world["requirement"].accepted_types = [PDF]
    world["requirement"].save()
    application = draft(world)
    wrong = ready_file(world["user"], sniffed_type=PNG)
    response = signed_in(client, world["user"]).post(
        doc_url(application, world["requirement"]), {"file": str(wrong.pk)}
    )
    assert response.status_code == 400
    body = response.content.decode()
    pk = world["requirement"].pk
    banner = body.index("banner--danger")
    assert banner < body.index(f'id="doc-{pk}"')
    assert f'<a href="#doc-{pk}">Grades document</a>' in body[banner:]
    assert "Check the Grades document below." in text(response).replace(
        f'<a href="#doc-{pk}">Grades document</a>', "Grades document"
    )


def test_document_post_error_without_a_row_shows_in_the_banner(client, world):
    application = draft(world)
    elsewhere = RequiredDocumentFactory.create(label="Elsewhere")  # another program's document
    response = signed_in(client, world["user"]).post(doc_url(application, elsewhere), {"file": ""})
    assert response.status_code == 400
    body = response.content.decode()
    assert "banner--danger" in body
    assert "Upload a file first." in text(response)
    assert "Elsewhere" not in body


def test_document_post_empty_file_shows_row_error(client, world):
    application = draft(world)
    response = signed_in(client, world["user"]).post(
        doc_url(application, world["requirement"]), {"file": ""}
    )
    assert response.status_code == 400
    assert "field__error" in response.content.decode()


def test_document_post_other_student_404(client, world):
    application = draft(world)
    other = UserFactory.create(verified=True)
    file = ready_file(other)
    response = signed_in(client, other).post(
        doc_url(application, world["requirement"]), {"file": str(file.pk)}
    )
    assert response.status_code == 404


def test_document_get_405(client, world):
    application = draft(world)
    response = signed_in(client, world["user"]).get(doc_url(application, world["requirement"]))
    assert response.status_code == 405
