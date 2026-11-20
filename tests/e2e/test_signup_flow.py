import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flows import sign_up_and_verify

pytestmark = pytest.mark.e2e


def test_sign_up_verify_and_land_on_the_student_home(
    page: Page, live_server, vite_build, mailoutbox, console_errors
):
    sign_up_and_verify(page, live_server.url, mailoutbox, "Ana Cruz", "ana.cruz@scholarsync.test")
    expect(page.get_by_role("heading", level=1)).to_have_text(
        re.compile(r"^Good (morning|afternoon|evening), Ana$")
    )
    assert console_errors == []
