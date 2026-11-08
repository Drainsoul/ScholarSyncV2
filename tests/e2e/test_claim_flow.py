from datetime import date

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.programs.tests.factories import MembershipFactory
from apps.students.services import create_staff_profile

pytestmark = pytest.mark.e2e

TOKEN = "e2e-fixed-claim-token"  # noqa: S105
EMAIL = "paolo.claim@scholarsync.test"


def test_student_claims_a_staff_created_profile(
    page: Page, live_server, vite_build, monkeypatch, console_errors
):
    # The outbox empties its context once sent, so pin the token the service generates.
    monkeypatch.setattr("apps.students.services.secrets.token_urlsafe", lambda _n=None: TOKEN)
    membership = MembershipFactory.create()
    create_staff_profile(
        actor=membership.user,
        program=membership.program,
        first_name="Paolo",
        middle_name="",
        last_name="Villanueva",
        suffix="",
        birth_date=date(2007, 5, 1),
        email=EMAIL,
    )
    UserFactory.create(email=EMAIL, verified=True)
    claim_url = f"{live_server.url}/accounts/claim/{TOKEN}/"

    page.goto(claim_url)
    expect(page.get_by_text("with the email address this invitation was sent to")).to_be_visible()
    page.get_by_role("link", name="Sign in").click()
    page.locator("#login-form input[name=login]").fill(EMAIL)
    page.locator("#login-form input[name=password]").fill(DEFAULT_PASSWORD)
    page.get_by_role("button", name="Log in").click()

    expect(page).to_have_url(claim_url)
    expect(page.get_by_text("Claim the profile for Paolo Villanueva?")).to_be_visible()
    page.get_by_label("I have read the privacy notice").check()
    page.get_by_role("button", name="Claim profile").click()

    expect(page).to_have_url(f"{live_server.url}/me/profile/")
    expect(page.get_by_text("Profile claimed. Check that your details are right.")).to_be_visible()
    expect(page.get_by_text("Paolo Villanueva").first).to_be_visible()
    assert console_errors == []
