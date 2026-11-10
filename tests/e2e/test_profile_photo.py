import pytest
from playwright.sync_api import Page, expect

from apps.accounts.tests.factories import UserFactory
from tests.e2e.flows import PNG, log_in, payload

pytestmark = pytest.mark.e2e

PHOTO_URL = "/me/profile/photo/"


def test_upload_a_profile_photo(page: Page, live_server, vite_build, e2e_storage, console_errors):
    user = UserFactory.create(verified=True)
    log_in(page, live_server.url, user.email, PHOTO_URL)
    expect(page.get_by_role("heading", level=1)).to_have_text("Profile photo")

    page.get_by_label("Photo", exact=True).set_input_files(
        files=payload("me.png", "image/png", PNG)
    )
    expect(page.locator(".file-input__status")).to_have_text("me.png uploaded")
    page.get_by_role("button", name="Save photo").click()

    expect(page.get_by_text("Photo saved.")).to_be_visible()
    page.goto(f"{live_server.url}{PHOTO_URL}")
    image = page.locator("img.profile-photo")
    expect(image).to_be_visible()
    page.wait_for_function("document.querySelector('img.profile-photo').naturalWidth > 0")
    assert image.evaluate("el => el.naturalWidth") > 0
    assert console_errors == []
