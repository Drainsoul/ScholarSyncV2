import re
from pathlib import Path

import pytest

from apps.kit.views import SWATCHES, icon_names

STYLES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "styles"


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_kit_answers_404_when_off(client, settings):
    settings.KIT_ENABLED = False
    assert client.get("/_kit/").status_code == 404


def test_kit_index_renders_the_foundations(client, kit_on, vite_build):
    response = client.get("/_kit/")
    body = response.content.decode()
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert body.count("<h1") == 1
    for section in ("colour", "type", "icons"):
        assert f'<section class="kit-section" id="{section}"' in body
    assert "/static/dist/assets/kit-" in body


def test_kit_shows_every_icon(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    for name in icon_names():
        assert f"icons.svg#{name}" in body


def test_every_swatch_is_a_token_with_a_kit_style():
    tokens = (STYLES / "tokens.css").read_text(encoding="utf-8")
    kit = (STYLES / "kit.css").read_text(encoding="utf-8")
    for name in SWATCHES:
        assert re.search(rf"--{name}:", tokens), name
        assert re.search(rf"\.kit-swatch--{name}\s*\{{\s*background:\s*var\(--{name}\);", kit), name


def test_kit_shows_controls_in_every_state(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<section class="kit-section" id="controls"' in body
    for marker in ("btn--primary", "btn--secondary", "btn--ghost", "btn--danger", " disabled>"):
        assert marker in body
    assert 'aria-invalid="true"' in body
    assert '<div class="alert alert--danger" role="alert">' in body
    assert "<progress" in body
    assert "&lt;img src=x&gt;" in body  # echoed invalid choice, escaped


def test_kit_shows_data_components(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<section class="kit-section" id="data"' in body
    for marker in ('class="stat ', 'class="pill pill--', 'class="card"', 'class="tabs"',
                   'aria-label="Breadcrumb"', 'class="empty"', "<meter", 'class="steps"',
                   'class="timeline"', 'aria-sort="ascending"'):  # fmt: skip
        assert marker in body, marker


def test_kit_table_filters_sorts_and_survives_bad_input(client, kit_on, vite_build):
    body = client.get("/_kit/?q=shaw").content.decode()
    assert "David Shaw" in body
    assert "William Heath" not in body
    for query in ("?page=abc", "?page=999", "?sort=__class__", "?status=nope"):
        assert client.get(f"/_kit/{query}").status_code == 200
    empty = client.get("/_kit/?q=nobody-has-this-name").content.decode()
    assert "No scholars match these filters" in empty
