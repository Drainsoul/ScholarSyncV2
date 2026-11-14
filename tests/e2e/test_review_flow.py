import pytest
from playwright.sync_api import Page, expect

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.programs.models import BenefitTier
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from tests.e2e.flows import log_in, one_kb_pdf, payload, submitted_application

pytestmark = pytest.mark.e2e

QUEUE = "/staff/tcu-ceaa/applications/"


def _staff_program():
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    membership = MembershipFactory.create(program=program, user__verified=True)
    return program, membership.user


def test_staff_review_approve_creates_award(page: Page, live_server, vite_build, console_errors):
    program, staff = _staff_program()
    application = submitted_application(program, first_name="Marisol")
    log_in(page, live_server.url, staff.email, "/staff/tcu-ceaa/")

    page.get_by_role("link", name="Applications").first.click()
    page.get_by_role("link", name=application.profile.full_name).click()
    page.get_by_role("button", name="Start review").click()
    expect(page.get_by_text("0 of 2 documents approved").first).to_be_visible()

    for label in ("Document 1", "Document 2"):
        page.get_by_role("button", name=f"Approve {label}").click()
        expect(page.get_by_role("row", name=label).get_by_text("Approved")).to_be_visible()
    expect(page.get_by_text("2 of 2 documents approved").first).to_be_visible()

    page.get_by_label("Approve", exact=True).check()
    page.get_by_label("Allowance tier").select_option(
        value=str(BenefitTier.objects.get(program=program).pk)
    )
    page.get_by_role("button", name="Save decision").click()

    expect(page.locator(".review-head .status").get_by_text("Approved", exact=True)).to_be_visible()
    award = Award.objects.get()
    assert award.status == Award.Status.ACTIVE
    assert award.source_application_id == application.pk
    assert ScholarTerm.objects.filter(award=award).count() == 1
    assert console_errors == []


def test_decline_in_dialog_then_return_then_student_resubmits(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    program, staff = _staff_program()
    application = submitted_application(program, first_name="Marisol", documents=2)
    base = live_server.url
    log_in(page, base, staff.email, f"/staff/tcu-ceaa/applications/{application.pk}/")

    page.get_by_role("button", name="Start review").click()
    page.get_by_role("link", name="Decline Document 1").click()
    dialog = page.get_by_role("dialog", name="Decline Document 1")
    expect(dialog).to_be_visible()

    dialog.get_by_label("Reason").fill("The scan is cut off at the bottom.")
    dialog.get_by_role("button", name="Decline document").click()
    expect(page.get_by_text("Document declined.")).to_be_visible()
    expect(page.get_by_text("The scan is cut off at the bottom.")).to_be_visible()
    page.get_by_role("button", name="Approve Document 2").click()
    expect(page.get_by_role("row", name="Document 2").get_by_text("Approved")).to_be_visible()

    page.get_by_label("Return for changes").check()
    page.get_by_label("Reason or note").fill("Please upload a clearer Document 1.")
    page.get_by_role("button", name="Save decision").click()
    expect(page.locator(".review-head .status").get_by_text("Returned", exact=True)).to_be_visible()
    application.refresh_from_db()
    assert application.status == Application.Status.RETURNED

    # The student signs in, sees the return and the reason, re-uploads and resubmits.
    page.context.clear_cookies()
    log_in(page, base, application.profile.user.email, f"/me/applications/{application.pk}/")
    expect(
        page.get_by_text("Staff returned this application: Please upload a clearer Document 1.")
    ).to_be_visible()
    expect(page.get_by_text("Declined: The scan is cut off at the bottom.")).to_be_visible()
    row = page.locator("li[id^=doc-]").filter(has=page.locator("input[type=file]"))
    upload = payload("document-1-again.pdf", "application/pdf", one_kb_pdf())
    row.locator("input[type=file]").set_input_files(files=upload)
    expect(row.locator(".file-input__status")).to_have_text(f"{upload['name']} uploaded")
    row.get_by_role("button", name="Save document").click()
    expect(page.get_by_text("Document saved.").first).to_be_visible()
    page.get_by_label(
        "I declare that the information and documents I have given are true and complete, "
        "and I agree that the scholarship office may check them."
    ).check()
    page.get_by_role("button", name="Resubmit application").click()
    expect(page.get_by_text("Application submitted. We've emailed you a copy.")).to_be_visible()

    # Staff sees it under Waiting again.
    page.context.clear_cookies()
    log_in(page, base, staff.email, QUEUE)
    expect(page.get_by_role("link", name=application.profile.full_name)).to_be_visible()
    assert console_errors == []


def test_bulk_start_review_from_the_queue(page: Page, live_server, vite_build, console_errors):
    program, staff = _staff_program()
    submitted_application(program, first_name="Ana")
    submitted_application(program, first_name="Bea")
    log_in(page, live_server.url, staff.email, QUEUE)

    page.get_by_label("Select all applications on this page").check()
    page.get_by_label("Action for the selected applications").select_option("start_review")
    page.get_by_role("button", name="Apply to selected").click()
    expect(page.get_by_text("Started review of 2 applications.")).to_be_visible()
    started = Application.objects.filter(status=Application.Status.UNDER_REVIEW, program=program)
    assert started.count() == 2
    assert console_errors == []


def test_queue_filters_without_js(browser, live_server, vite_build):
    program, staff = _staff_program()
    submitted_application(program, first_name="Ana")
    submitted_application(program, first_name="Bea", status=Application.Status.APPROVED)
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    try:
        log_in(page, live_server.url, staff.email, QUEUE)
        expect(page.locator("tbody tr")).to_have_count(1)
        expect(page.locator("tbody tr")).to_contain_text("Ana")
        page.locator("#filter-status").select_option("approved")
        page.get_by_role("button", name="Apply filters").click()
        expect(page.locator("tbody tr")).to_have_count(1)
        expect(page.locator("tbody tr")).to_contain_text("Bea")
        expect(page.locator("tbody tr")).to_contain_text("Approved")
    finally:
        context.close()


def test_review_page_at_375px_has_no_horizontal_scroll(
    page: Page, live_server, vite_build, console_errors
):
    program, staff = _staff_program()
    application = submitted_application(program, first_name="Marisol")
    page.set_viewport_size({"width": 375, "height": 800})
    log_in(page, live_server.url, staff.email, f"/staff/tcu-ceaa/applications/{application.pk}/")

    expect(page.get_by_role("heading", level=1)).to_contain_text("Marisol")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert console_errors == []
