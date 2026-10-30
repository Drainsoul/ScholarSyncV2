"""Spec §12 rev 4 rules that every kit page and mockup keeps."""

import re
from html.parser import HTMLParser

import pytest

from apps.kit.views import LAYOUTS, MOCKUPS


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


KIT_PAGES = ["/_kit/"] + [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]
ALL_PAGES = KIT_PAGES + ["/_kit/mockups/"] + [f"/_kit/layouts/{name}/" for name in LAYOUTS]
STATUS_TONES = {"success", "warning", "info", "danger", "neutral"}
# Icons that carry meaning on a button (spec §12): every other button is text only.
BUTTON_ICONS = {
    "download", "x", "menu", "log-out", "plus", "mail", "circle-pause", "chevron-left",
    "chevron-right", "filter",
}  # fmt: skip


@pytest.mark.parametrize("url", KIT_PAGES)
def test_buttons_carry_no_decorative_icons(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    pattern = r'<(?:a|button)[^>]*class="btn[^"]*"[^>]*>(.*?)</(?:a|button)>'
    for button in re.findall(pattern, body, re.S):
        assert set(re.findall(r"icons\.svg#([a-z0-9-]+)", button)) <= BUTTON_ICONS, button


def test_form_errors_render_an_error_summary(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<div class="banner banner--danger" role="alert">' in body
    assert "There is a problem" in body


@pytest.mark.parametrize("url", ALL_PAGES)
def test_status_is_coloured_text_not_a_tag(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    assert 'class="tag' not in body
    assert 'class="pill' not in body
    statuses = re.findall(r'<span class="status status--([a-z-]+)">(.*?)</span>', body, re.S)
    for tone, text in statuses:
        assert "<svg" not in text, text
        assert re.sub(r"<[^>]+>", "", text).strip(), tone
    assert {tone for tone, _ in statuses} <= STATUS_TONES
    # Every status element is one of the matched spans: none slips past with other markup.
    assert body.count('class="status ') == len(statuses)


def test_kit_shows_every_status_tone(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    for tone in STATUS_TONES:
        assert f'<span class="status status--{tone}">' in body, tone


class Within(HTMLParser):
    """Collects the inner HTML-ish text of every element carrying a class (depth-tracked)."""

    VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}

    def __init__(self, class_name: str) -> None:
        super().__init__()
        self.class_name = class_name
        self.depth = 0  # open elements inside the current match, 0 when outside
        self.found: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if self.depth:
            self.found[-1].append(f"<{tag} class={' '.join(classes)}>")
            if tag not in self.VOID:
                self.depth += 1
        elif self.class_name in classes and tag not in self.VOID:
            self.found.append([])
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in self.VOID:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.found[-1].append(data)


@pytest.mark.parametrize("url", KIT_PAGES)
def test_figures_box_has_no_icons_or_notes(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    assert "figure__note" not in body
    assert "stat__chip" not in body
    parser = Within("figures")
    parser.feed(body)
    for box in parser.found:
        inner = "".join(box)
        assert "<svg" not in inner, inner
        assert "<progress" not in inner and "<meter" not in inner, inner


class CardDepth(HTMLParser):
    """Records every element with the card class that opens inside another card."""

    VOID = Within.VOID

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
def test_pages_have_no_middle_dot_meta(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    page = body[body.index("<body") :]  # the document title may keep its separator
    assert "·" not in page  # no middle-dot meta strings


def test_kit_copy_describes_the_redesign(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    for current in ("Lexend", "Source Sans 3", "Figures", "red"):
        assert current in body, current
    for stale in ("navy", "Swiss"):
        assert not re.search(stale, body, re.I), stale


class Banners(HTMLParser):
    """Records each banner's modifier classes and whether an icon sits anywhere inside it."""

    VOID = Within.VOID

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


def test_file_input_error_sits_above_the_control_without_an_icon(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    block = re.search(r'<div class="file-input field--invalid">(.*?)</div>', body, re.S)
    assert block, "the error state marks the file input invalid"
    html = block.group(1)
    error = re.search(r'<p class="field__error" id="file-error-error">(.*?)</p>', html, re.S)
    assert error
    assert "<svg" not in error.group(1)
    assert html.index('id="file-error-error"') < html.index('<input class="file-input__control"')


def test_student_dashboard_has_a_service_title(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/student-dashboard/").content.decode()
    assert "<h1>Your scholarships</h1>" in body
    assert "Hello" not in body
    meta = re.search(r'<p class="page-header__meta">(.*?)</p>', body)
    assert meta and "Carolyn Hawkins" in meta.group(1)


def test_kit_shows_every_component_state(client, kit_on, vite_build):
    """The kit is the reference for later tasks: each new component appears in every state."""
    body = client.get("/_kit/").content.decode()
    for variant in ("primary", "secondary", "soft", "ghost", "danger"):
        assert f'class="btn btn--{variant}"' in body, variant
    for tone in ("red", "blue", "yellow"):
        assert f'class="avatar avatar--{tone}"' in body, tone
    assert 'class="avatar avatar--red avatar--lg"' in body
    for count in ('class="count"', 'class="count count--accent"', 'class="count count--current"'):
        assert count in body, count
    for tone in ("primary", "secondary", "success"):
        progress = rf'<progress class="progress progress--{tone}" max="\d+" value="\d+"'
        assert re.search(progress, body), tone
    assert body.count('<a class="row-link"') >= 3
    assert re.search(r'<aside class="drawer" id="kit-drawer" tabindex="-1"', body)
    assert 'class="table-toolbar' in body
    assert 'aria-current="page"' in body
    assert 'class="figures"' in body
    assert 'class="section' not in body  # sections inside pages are cards now
    assert 'class="panel' not in body
