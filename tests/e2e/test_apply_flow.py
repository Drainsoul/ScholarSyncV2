import re

import pytest
from django.core.management import call_command
from playwright.sync_api import Page, expect

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.programs.models import AcademicTerm, Program, School
from apps.programs.selectors import required_documents_for
from apps.students.tests.factories import EducationRecordFactory, ProfileFactory
from tests.e2e.flows import (
    PNG,
    fill_personal_details,
    log_in,
    one_kb_pdf,
    payload,
    sign_up_and_verify,
)

pytestmark = pytest.mark.e2e

MATCH_PATH = "/me/match/"
DECLARATION = (
    "I declare that the information and documents I have given are true and complete, "
    "and I agree that the scholarship office may check them."
)


def test_sign_up_verify_profile_match_apply(
    page: Page, live_server, vite_build, e2e_storage, mailoutbox, console_errors
):
    call_command("seed_programs")
    base = live_server.url
    sign_up_and_verify(page, base, mailoutbox, "Carolyn Hawkins", "carolyn@scholarsync.test")
    fill_personal_details(page, base)

    page.goto(f"{base}/me/profile/education/add/")
    page.locator("#id_level").select_option("college")
    page.locator("#id_school").select_option(label="Taguig City University")
    page.locator("#id_course").fill("BS Information Technology")
    page.locator("#id_year_level").fill("2")
    page.locator("#id_gwa").fill("90")
    page.locator("#id_units").fill("21")
    page.get_by_label("I'm studying here now").check()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Education")

    page.goto(f"{base}{MATCH_PATH}")
    expect(page.get_by_role("heading", level=1)).to_have_text("Find scholarships")
    ceaa = page.locator("section.card").filter(has=page.get_by_role("heading", name="TCU CEAA"))
    expect(ceaa).to_contain_text("You qualify")
    ceaa.get_by_role("link", name="Apply").click()
    page.get_by_role("button", name="Start application").click()
    expect(page.get_by_text("Application started.")).to_be_visible()

    program = Program.objects.get(slug="tcu-ceaa")
    required = required_documents_for(program, "new").filter(is_required=True)
    assert required.exists()
    for requirement in required:
        row = page.locator(f"li[id^=doc-]:has(form[action$='/{requirement.pk}/'])")
        if "application/pdf" in requirement.accepted_types:
            upload = payload("document.pdf", "application/pdf", one_kb_pdf())
        else:
            upload = payload("document.png", "image/png", PNG)
        row.locator("input[type=file]").set_input_files(files=upload)
        expect(row.locator(".file-input__status")).to_have_text(f"{upload['name']} uploaded")
        row.get_by_role("button", name="Save document").click()
        expect(page.get_by_text("Document saved.").first).to_be_visible()

    page.get_by_label(DECLARATION).check()
    page.get_by_role("button", name="Submit application").click()
    expect(page.get_by_text("Application submitted. We've emailed you a copy.")).to_be_visible()

    page.goto(f"{base}/me/applications/")
    expect(page.locator("tbody tr").filter(has_text="TCU CEAA Scholarship")).to_contain_text(
        "Submitted"
    )
    assert console_errors == []


def test_ineligible_student_sees_reasons_and_no_apply_link(
    page: Page, live_server, vite_build, console_errors
):
    call_command("seed_programs")
    ust = School.objects.get(name="University of Santo Tomas")
    user = UserFactory.create(verified=True)
    profile = ProfileFactory.create(user=user)
    EducationRecordFactory.create(
        profile=profile,
        school=ust,
        gwa="3.50",
        gwa_scale=School.Scale.ONE_TO_FIVE,
        units=21,
        year_level=2,
    )
    log_in(page, live_server.url, user.email, MATCH_PATH)

    expect(page.get_by_role("heading", level=1)).to_have_text("Find scholarships")
    lani = page.locator("section.card").filter(has=page.get_by_role("heading", name="LANI"))
    ceaa = page.locator("section.card").filter(has=page.get_by_role("heading", name="TCU CEAA"))
    expect(lani).to_contain_text("Not yet")
    expect(lani).to_contain_text("Your GWA of 3.50 doesn't meet this program's maximum of 3.00.")
    expect(ceaa).to_contain_text("Not yet")
    expect(ceaa).to_contain_text(re.compile("Taguig City University", re.IGNORECASE))
    expect(page.get_by_role("link", name="Apply")).to_have_count(0)
    assert console_errors == []


def test_withdraw_flow(page: Page, live_server, vite_build, console_errors):
    call_command("seed_programs")
    program = Program.objects.get(slug="tcu-ceaa")
    term = AcademicTerm.objects.filter(is_current=True).first() or AcademicTerm.objects.first()
    assert term is not None
    user = UserFactory.create(verified=True)
    profile = ProfileFactory.create(user=user)
    application = ApplicationFactory.create(profile=profile, program=program, term=term)
    log_in(page, live_server.url, user.email, f"/me/applications/{application.pk}/")

    page.get_by_role("link", name="Withdraw application").click()
    page.get_by_role("button", name="Withdraw application").click()
    expect(page.get_by_text("Application withdrawn.")).to_be_visible()

    page.goto(f"{live_server.url}/me/applications/")
    expect(page.locator("tbody tr").filter(has_text="TCU CEAA Scholarship")).to_contain_text(
        "Withdrawn"
    )
    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN
    assert console_errors == []


def test_match_page_phone_width(page: Page, live_server, vite_build, console_errors):
    call_command("seed_programs")
    user = UserFactory.create(verified=True)
    ProfileFactory.create(user=user)
    page.set_viewport_size({"width": 375, "height": 800})
    log_in(page, live_server.url, user.email, MATCH_PATH)

    expect(page.get_by_role("heading", level=1)).to_have_text("Find scholarships")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert console_errors == []
