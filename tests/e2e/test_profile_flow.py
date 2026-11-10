import pytest
from django.core.management import call_command
from playwright.sync_api import Page, expect

from apps.accounts.tests.factories import UserFactory
from tests.e2e.flows import fill_personal_details, log_in

pytestmark = pytest.mark.e2e

PROFILE_PAGES = [
    "/me/",
    "/me/profile/",
    "/me/profile/personal/",
    "/me/profile/family/",
    "/me/profile/family/add/",
    "/me/profile/education/",
    "/me/profile/education/add/",
    "/me/profile/photo/",
]


def test_a_new_student_fills_in_the_profile(page: Page, live_server, vite_build, console_errors):
    call_command("seed_programs")
    user = UserFactory.create(verified=True)
    base = live_server.url
    log_in(page, base, user.email)
    expect(page.locator(".profile-figure")).to_contain_text("0% complete")

    fill_personal_details(page, base)

    page.goto(f"{base}/me/profile/family/add/")
    page.get_by_label("Relation").select_option("guardian")
    page.get_by_label("Name").fill("Teresa Hawkins")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Teresa Hawkins")).to_be_visible()

    page.goto(f"{base}/me/profile/education/add/")
    page.locator("#id_level").select_option("college")
    page.locator("#id_school").select_option(label="Taguig City University")
    page.locator("#id_course").fill("BS Information Technology")
    page.get_by_label("I'm studying here now").check()
    page.get_by_role("button", name="Save").click()

    page.goto(f"{base}/me/profile/")
    expect(page.locator(".page-header__meta")).to_have_text("92% complete")
    expect(page.get_by_text("Missing: a photo")).to_be_visible()
    expect(page.get_by_text("Missing:")).to_have_count(1)

    page.set_viewport_size({"width": 375, "height": 800})
    for path in PROFILE_PAGES:
        page.goto(f"{base}{path}")
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"{path} scrolls horizontally"
    assert console_errors == []
