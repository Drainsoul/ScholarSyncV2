import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_sign_up_verify_and_land_on_the_student_home(
    page: Page, live_server, vite_build, mailoutbox, console_errors
):
    page.goto(f"{live_server.url}/accounts/signup/")
    page.get_by_label("Full name").fill("Ana Cruz")
    page.get_by_label("Email").fill("ana.cruz@scholarsync.test")
    page.get_by_label("Password", exact=True).fill("signup-pass-2026")
    page.get_by_label("Password (again)").fill("signup-pass-2026")
    page.get_by_label("I have read the privacy notice").check()
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Check your email")
    match = re.search(r"https?://\S+/accounts/confirm-email/\S+/", mailoutbox[0].body)
    assert match is not None
    page.goto(match.group(0))
    page.get_by_role("button", name="Confirm").click()
    expect(page).to_have_url(f"{live_server.url}/me/")
    expect(page.get_by_role("heading", level=1)).to_have_text("Your scholarships")
    assert console_errors == []
