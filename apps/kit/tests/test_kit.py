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
