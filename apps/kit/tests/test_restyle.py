import re

import pytest

from apps.kit.views import MOCKUPS


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


KIT_PAGES = ["/_kit/"] + [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]


@pytest.mark.parametrize("url", KIT_PAGES)
def test_tags_are_text_only(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    tags = re.findall(r'<span class="tag[^"]*">(.*?)</span>', body, re.S)
    for tag in tags:
        assert "<svg" not in tag
        assert re.sub(r"<[^>]+>", "", tag).strip()
    assert 'class="pill' not in body


@pytest.mark.parametrize("url", KIT_PAGES)
def test_figures_have_no_icon_chips(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    assert "stat__chip" not in body
    for figure in re.findall(r'<div class="figure">(.*?)</div>', body, re.S):
        assert "<svg" not in figure
