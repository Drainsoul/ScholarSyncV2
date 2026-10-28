import json
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


def test_kit_table_sorts_rows_and_pagination_links_stay_clean(client, kit_on, vite_build):
    body = client.get("/_kit/?sort=-amount").content.decode()
    rows = body[body.index("<tbody") : body.index("</tbody>")]
    assert rows.index("₱10,000.00") < rows.index("₱7,500.00")
    plain = client.get("/_kit/").content.decode()
    assert 'href="?page=2"' in plain


def test_htmx_filter_returns_only_the_table_partial(client, kit_on, vite_build):
    response = client.get(
        "/_kit/?q=shaw", headers={"HX-Request": "true", "HX-Target": "scholars-table"}
    )
    body = response.content.decode()
    assert body.lstrip().startswith('<div id="scholars-table"')
    assert "<html" not in body
    assert "David Shaw" in body


def test_demo_toast_over_htmx_returns_204_with_a_trigger(client, kit_on):
    response = client.post(
        "/_kit/demo/toast/", {"message": "Saved", "tone": "warning"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 204
    assert json.loads(response["HX-Trigger"]) == {"toast": {"message": "Saved", "tone": "warning"}}


def test_demo_toast_without_htmx_uses_messages(client, kit_on, vite_build):
    response = client.post("/_kit/demo/toast/", {"message": "Saved", "tone": "danger"}, follow=True)
    body = response.content.decode()
    assert '<div class="toast toast--danger" data-toast data-tone="danger">' in body
    assert "Saved" in body


def test_demo_toast_rejects_unknown_tones(client, kit_on):
    response = client.post(
        "/_kit/demo/toast/", {"message": "x", "tone": "evil"}, headers={"HX-Request": "true"}
    )
    assert json.loads(response["HX-Trigger"])["toast"]["tone"] == "info"
