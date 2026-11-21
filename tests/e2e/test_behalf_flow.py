from datetime import date
from decimal import Decimal

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.programs.models import Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.students.services import create_staff_profile
from apps.students.tests.factories import ProfileFactory
from tests.e2e.flows import log_in, one_kb_pdf, payload, submitted_application

pytestmark = pytest.mark.e2e

TOKEN = "e2e-behalf-claim-token"  # noqa: S105
EMAIL = "rina.walkin@scholarsync.test"
SLUG = "tcu-ceaa"
REFUSED_400 = "Failed to load resource: the server responded with a status of 400 (Bad Request)"


def _program() -> tuple[Program, User]:
    """TCU CEAA: GWA 80% and Taguig City University, one tier, two required documents."""
    school = SchoolFactory.create(name="Taguig City University", is_in_taguig=True)
    program = ProgramFactory.create(slug=SLUG, name="TCU CEAA", min_gwa_percent=Decimal("80"))
    program.allowed_schools.add(school)
    term = AcademicTermFactory.create(school_year_start=2026, is_current=True)
    BenefitTierFactory.create(program=program, effective_from=term, code="full", name="Full")
    for index in (1, 2):
        RequiredDocumentFactory.create(
            program=program, code=f"doc-{index}", label=f"Document {index}", sort_order=index
        )
    staff = MembershipFactory.create(program=program, user__verified=True).user
    return program, staff


def _upload_row(page: Page, index: int) -> None:
    row = page.locator("li[id^=doc-]").nth(index)
    upload = payload(f"document-{index + 1}.pdf", "application/pdf", one_kb_pdf())
    row.locator("input[type=file]").set_input_files(files=upload)
    expect(row.locator(".file-input__status")).to_have_text(f"{upload['name']} uploaded")
    row.get_by_role("button", name="Save document").click()
    expect(page.get_by_text("Document saved.").first).to_be_visible()


def test_staff_files_for_walk_in(page: Page, live_server, vite_build, e2e_storage, console_errors):
    _, staff = _program()
    log_in(page, live_server.url, staff.email, f"/staff/{SLUG}/students/")

    page.get_by_role("link", name="New profile").click()
    page.get_by_label("First name").fill("Rina")
    page.get_by_label("Last name").fill("Walkin")
    page.get_by_label("Birth date").fill("2006-02-03")
    page.get_by_label("Student's email").fill(EMAIL)
    page.get_by_role("button", name="Create and send invitation").click()
    expect(page.get_by_text("Profile created and invitation sent.")).to_be_visible()

    page.get_by_role("link", name="File for a student").first.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("File for a student")
    page.get_by_role("button", name="File an application").click()
    expect(page.get_by_text("Application started for Rina Walkin.")).to_be_visible()

    page.get_by_label("School", exact=True).select_option(label="Taguig City University")
    page.get_by_label("Course").fill("BS Information Technology")
    page.get_by_label("Year level").fill("2")
    page.get_by_label("GWA").fill("78")
    page.get_by_label("Units").fill("21")
    page.get_by_role("button", name="Save school and grades").click()
    expect(page.get_by_text("School and grades saved.")).to_be_visible()

    for index in (0, 1):
        _upload_row(page, index)
    expect(page.get_by_text("2 of 2 required documents uploaded")).to_be_visible()
    expect(
        page.get_by_text("Staff can file even when a rule isn't met. Say why below.")
    ).to_be_visible()

    page.get_by_role("button", name="Submit application").click()
    expect(
        page.get_by_text(
            "This student doesn't meet every rule. Say why you're filing anyway."
        ).first
    ).to_be_visible()

    page.get_by_label("Reason for filing anyway").fill("Walk-in; the registrar confirmed 80%.")
    page.get_by_role("button", name="Submit application").click()
    expect(page.get_by_text("Submitted Rina Walkin's application.")).to_be_visible()
    expect(page.get_by_text("Filed by").first).to_be_visible()
    expect(page.get_by_text("Overridden by staff").first).to_be_visible()

    application = Application.objects.get()
    assert application.status == Application.Status.SUBMITTED
    assert application.on_behalf

    page.goto(f"{live_server.url}/staff/{SLUG}/applications/")
    expect(page.locator("#filter-status")).to_have_value("waiting")
    expect(page.get_by_role("link", name="Rina Walkin")).to_be_visible()
    # The refused submit without a reason is the one expected 400.
    assert console_errors == [REFUSED_400]


def test_claimed_student_sees_read_only(
    page: Page, live_server, vite_build, monkeypatch, console_errors
):
    monkeypatch.setattr("apps.students.services.secrets.token_urlsafe", lambda _n=None: TOKEN)
    program, staff = _program()
    profile, _invite = create_staff_profile(
        actor=staff,
        program=program,
        first_name="Rina",
        middle_name="",
        last_name="Walkin",
        suffix="",
        birth_date=date(2006, 2, 3),
        email=EMAIL,
    )
    tier = program.tiers.get()
    application = ApplicationFactory.create(
        profile=profile,
        program=program,
        term=tier.effective_from,
        status=Application.Status.SUBMITTED,
        school_name="Taguig City University",
        course="BS Information Technology",
        year_level=2,
        gwa=Decimal("90.00"),
        gwa_scale="percent",
        units=21,
        on_behalf=True,
        created_by=staff,
        requested_tier=tier,
    )
    for requirement in program.required_documents.all():
        document = DocumentFactory.create(application=application, requirement=requirement)
        DocumentFileFactory.create(document=document, file__uploaded_by=staff)
    UserFactory.create(email=EMAIL, verified=True)

    claim_url = f"{live_server.url}/accounts/claim/{TOKEN}/"
    page.goto(claim_url)
    page.get_by_role("link", name="Sign in").click()
    page.locator("#login-form input[name=login]").fill(EMAIL)
    page.locator("#login-form input[name=password]").fill(DEFAULT_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.get_by_label("I have read the privacy notice").check()
    page.get_by_role("button", name="Claim profile").click()
    expect(page.get_by_text("Profile claimed.")).to_be_visible()

    page.goto(f"{live_server.url}/me/applications/{application.pk}/")
    expect(page.get_by_text("TCU CEAA staff filed this application for you.")).to_be_visible()
    expect(page.locator("input[type=file]")).to_have_count(0)
    expect(page.get_by_role("button", name="Withdraw application")).to_have_count(0)
    expect(page.get_by_role("button", name="Save document")).to_have_count(0)
    assert console_errors == []


def test_return_and_resubmit_by_staff(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    program, staff = _program()
    application = submitted_application(
        program, first_name="Marisol", documents=2, on_behalf=True, created_by=staff
    )
    log_in(page, live_server.url, staff.email, f"/staff/{SLUG}/applications/{application.pk}/")

    page.get_by_role("button", name="Start review").click()
    page.get_by_role("link", name="Decline Document 1").click()
    dialog = page.get_by_role("dialog", name="Decline Document 1")
    dialog.get_by_label("Reason").fill("The scan is cut off at the bottom.")
    dialog.get_by_role("button", name="Decline document").click()
    expect(page.get_by_text("Document declined.")).to_be_visible()
    page.get_by_role("button", name="Approve Document 2").click()
    expect(page.get_by_role("row", name="Document 2").get_by_text("Approved")).to_be_visible()

    page.get_by_label("Return for changes").check()
    page.get_by_label("Reason or note").fill("Please upload a clearer Document 1.")
    page.get_by_role("button", name="Save decision").click()
    expect(page.locator(".review-head .status").get_by_text("Returned", exact=True)).to_be_visible()

    page.get_by_role("link", name="Fix and resubmit").click()
    expect(page.get_by_text("Returned for fixes")).to_be_visible()
    row = page.locator("li[id^=doc-]").filter(has=page.locator("input[type=file]"))
    upload = payload("document-1-again.pdf", "application/pdf", one_kb_pdf())
    row.locator("input[type=file]").set_input_files(files=upload)
    expect(row.locator(".file-input__status")).to_have_text(f"{upload['name']} uploaded")
    row.get_by_role("button", name="Save document").click()
    expect(page.get_by_text("Document saved.").first).to_be_visible()
    page.get_by_role("button", name="Resubmit").click()

    expect(
        page.locator(".review-head .status").get_by_text("Submitted", exact=True)
    ).to_be_visible()
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert console_errors == []


def test_staff_finds_self_registered_student_by_email(
    page: Page, live_server, vite_build, console_errors
):
    _, staff = _program()
    student = UserFactory.create(email="mara.self@scholarsync.test", verified=True)
    ProfileFactory.create(user=student, created_for=None, first_name="Mara", last_name="Sy")
    log_in(page, live_server.url, staff.email, f"/staff/{SLUG}/applications/new/")

    expect(page.get_by_role("heading", name="Find a student by account email")).to_be_visible()
    page.get_by_label("Student's account email").fill("nobody@scholarsync.test")
    page.get_by_role("button", name="Find student").click()
    expect(page.get_by_text("No student account uses that email.")).to_be_visible()
    assert "scholarsync.test" not in page.url

    page.get_by_label("Student's account email").fill("Mara.Self@ScholarSync.test")
    page.get_by_role("button", name="Find student").click()
    expect(page.get_by_text("Found Mara Sy.")).to_be_visible()
    page.get_by_role("button", name="File an application for Mara Sy").click()
    expect(page.get_by_text("Application started for Mara Sy.")).to_be_visible()
    expect(page.get_by_role("button", name="Save school and grades")).to_be_visible()
    assert Application.objects.get().profile.user == student
    assert console_errors == []
