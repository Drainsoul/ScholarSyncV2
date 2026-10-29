import re
from html.parser import HTMLParser

import pytest

from apps.kit.views import LAYOUTS, MOCKUPS


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


KIT_PAGES = ["/_kit/"] + [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]
ALL_PAGES = KIT_PAGES + ["/_kit/mockups/"] + [f"/_kit/layouts/{name}/" for name in LAYOUTS]


@pytest.mark.parametrize("url", KIT_PAGES)
def test_buttons_carry_no_decorative_icons(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    allowed = {"download", "x", "menu", "log-out"}
    pattern = r'<(?:a|button)[^>]*class="btn[^"]*"[^>]*>(.*?)</(?:a|button)>'
    for button in re.findall(pattern, body, re.S):
        assert set(re.findall(r"icons\.svg#([a-z0-9-]+)", button)) <= allowed, button


def test_form_errors_render_an_error_summary(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<div class="banner banner--danger" role="alert">' in body
    assert "There is a problem" in body


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


class CardDepth(HTMLParser):
    """Records every element with the card class that opens inside another card."""

    VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[bool] = []
        self.nested: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.VOID:
            return
        is_card = "card" in (dict(attrs).get("class") or "").split()
        if is_card and any(self.stack):
            self.nested.append(tag)
        self.stack.append(is_card)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.VOID and self.stack:
            self.stack.pop()


@pytest.mark.parametrize("url", ALL_PAGES)
def test_no_card_sits_inside_another_card(client, kit_on, vite_build, url):
    parser = CardDepth()
    parser.feed(client.get(url).content.decode())
    assert parser.nested == []


@pytest.mark.parametrize("url", ALL_PAGES)
def test_pages_use_banners_and_plain_meta(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    assert 'class="alert' not in body
    page = body[body.index("<body") :]  # the document title may keep its separator
    assert "·" not in page  # no middle-dot meta strings


def test_kit_copy_describes_the_civic_design(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    for stale in ("Poppins", "Inter ", "Brand red is for actions", "Stat tiles", "pill", "sidebar"):
        assert stale not in body, stale
    for current in ("Lexend", "Source Sans 3", "Figures"):
        assert current in body, current
