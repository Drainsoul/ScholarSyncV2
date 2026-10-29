import re

import pytest


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_buttons_carry_no_decorative_icons(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    allowed = {"download", "x", "menu", "log-out"}
    pattern = r'<(?:a|button)[^>]*class="btn[^"]*"[^>]*>(.*?)</(?:a|button)>'
    for button in re.findall(pattern, body, re.S):
        assert set(re.findall(r"icons\.svg#([a-z0-9-]+)", button)) <= allowed, button


def test_form_errors_render_an_error_summary(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<div class="banner banner--danger" role="alert">' in body
    assert "There is a problem" in body
