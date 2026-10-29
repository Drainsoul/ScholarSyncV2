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
        assert not re.search(rf"{stale}", body), stale  # whole words: "pillar" is fine
    for current in ("Lexend", "Source Sans 3", "Figures"):
        assert current in body, current


class Banners(HTMLParser):
    """Records each banner's modifier classes and whether an icon sits anywhere inside it."""

    VOID = CardDepth.VOID

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[int | None] = []  # per open element: its index in found, if a banner
        self.found: list[list[str | bool]] = []  # [modifiers, has_icon]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.VOID:
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag == "svg":
            for index in (i for i in self.stack if i is not None):
                self.found[index][1] = True
        if "banner" in classes:
            self.found.append([" ".join(c for c in classes if c.startswith("banner--")), False])
            self.stack.append(len(self.found) - 1)
        else:
            self.stack.append(None)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.VOID and self.stack:
            self.stack.pop()


@pytest.mark.parametrize("url", KIT_PAGES)
def test_only_warning_and_danger_banners_carry_an_icon(client, kit_on, vite_build, url):
    parser = Banners()
    parser.feed(client.get(url).content.decode())
    assert parser.found or url != "/_kit/"
    with_icons = [mods or "info" for mods, has_icon in parser.found if has_icon]
    assert set(with_icons) <= {"banner--warning", "banner--danger"}, with_icons


@pytest.mark.parametrize("url", KIT_PAGES)
def test_tags_use_only_defined_tones(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    tones = set(re.findall(r'class="tag tag--([a-z-]+)"', body))
    assert tones <= {"success", "warning", "danger", "info"}, tones


def test_file_input_error_sits_above_the_control_without_an_icon(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    block = re.search(r'<div class="file-input field--invalid">(.*?)</div>', body, re.S)
    assert block, "the error state marks the file input invalid"
    html = block.group(1)
    error = re.search(r'<p class="field__error" id="file-error-error">(.*?)</p>', html, re.S)
    assert error
    assert "<svg" not in error.group(1)
    assert html.index('id="file-error-error"') < html.index('<input class="file-input__control"')


# Secondary regions are unboxed, ruled sections; panels are kept for tables and forms (spec §12).
SECTIONS = {
    "student-dashboard": ["award-title", "profile-title", "notices-title"],
    "apply": ["program-title", "match-title"],
    "application-review": ["applicant-title", "eligibility-title", "history-title"],
    "office-dashboard": ["attention-title", "activity-title"],
}


@pytest.mark.parametrize("slug", list(SECTIONS))
def test_secondary_regions_are_sections_not_panels(client, kit_on, vite_build, slug):
    body = client.get(f"/_kit/mockups/{slug}/").content.decode()
    for title in SECTIONS[slug]:
        assert f'<section class="section" aria-labelledby="{title}">' in body, title


def test_review_status_sits_on_the_meta_line(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/application-review/").content.decode()
    meta = re.search(r'<p class="page-header__meta">(.*?)</p>', body, re.S)
    assert meta and '<span class="tag tag--info">Under review</span>' in meta.group(1)


def test_student_dashboard_has_a_service_title(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/student-dashboard/").content.decode()
    assert "<h1>Your scholarships</h1>" in body
    assert "Hello" not in body
    meta = re.search(r'<p class="page-header__meta">(.*?)</p>', body)
    assert meta and "Carolyn Hawkins" in meta.group(1)


def test_kit_shows_an_unboxed_section(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert re.search(r'<section class="section[ "]', body)
