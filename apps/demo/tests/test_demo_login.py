"""One-click demo login. Lives in the demo folder so nothing outside it imports the demo."""

import pytest
from playwright.sync_api import Page, expect

from apps.demo import loader

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _e2e_db(transactional_db):
    """The live server answers from another thread, so tests need a transactional database."""


@pytest.mark.parametrize(
    ("button", "path", "email"),
    [
        ("Student", "/me/", "student@scholarsync.test"),
        ("Program staff", "/staff/tcu-ceaa/", "staff@scholarsync.test"),
        ("Program head", "/staff/tcu-ceaa/", "head@scholarsync.test"),
        ("Scholarship office", "/office/", "office@scholarsync.test"),
    ],
)
def test_one_click_fill_then_log_in(page: Page, live_server, vite_build, button, path, email):
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    loader.load()
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_role("button", name=button, exact=True).click()
    expect(page.locator("[data-fill-status]")).to_have_text(
        f"Filled in the {button} account. Press Log in."
    )
    expect(page.locator("#login-form [name=login]")).to_have_value(email)
    page.get_by_role("button", name="Log in").click()
    expect(page).to_have_url(f"{live_server.url}{path}")
    assert errors == []
