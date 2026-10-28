import json
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders

from apps.kit.views import SWATCHES, icon_names

STYLES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "styles"


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_kit_answers_404_when_off(client, settings, vite_build):
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


def test_icon_names_come_from_the_built_sprite(vite_build):
    sprite = Path(str(finders.find("dist/icons.svg"))).read_text(encoding="utf-8")
    names = icon_names()
    assert names
    assert names == re.findall(r'<symbol id="([^"]+)"', sprite)


def test_kit_index_renders_when_the_sprite_is_missing(client, kit_on, vite_build, monkeypatch):
    """Vercel ships no frontend/src and a preview may lack the sprite: the kit still renders."""
    monkeypatch.setattr(finders, "find", lambda *args, **kwargs: None)
    assert icon_names() == []
    assert client.get("/_kit/").status_code == 200


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
    body = client.get(
        "/_kit/?q=shaw", headers={"HX-Request": "true", "HX-Target": "scholars-table"}
    ).content.decode()
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


def test_index_varies_on_htmx_headers_for_full_page_and_partial(client, kit_on, vite_build):
    full = client.get("/_kit/")
    partial = client.get(
        "/_kit/?q=shaw", headers={"HX-Request": "true", "HX-Target": "scholars-table"}
    )
    for response in (full, partial):
        vary = response["Vary"]
        assert "HX-Request" in vary
        assert "HX-Target" in vary


def test_base_layout_has_the_dialog_shell(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<dialog id="app-dialog" class="dialog" aria-labelledby="app-dialog-title">' in body


def test_demo_dialog_is_a_page_without_htmx_and_a_fragment_with_it(client, kit_on, vite_build):
    page_response = client.get("/_kit/demo/dialog/")
    page = page_response.content.decode()
    assert "<h1>Release allowances</h1>" in page
    assert "HX-Request" in page_response["Vary"]
    fragment_response = client.get("/_kit/demo/dialog/", headers={"HX-Request": "true"})
    fragment = fragment_response.content.decode()
    assert "HX-Request" in fragment_response["Vary"]
    assert '<h2 class="dialog__title" id="app-dialog-title">Release allowances</h2>' in fragment
    assert "<html" not in fragment
    assert "₱60,000.00" in fragment


def test_demo_dialog_post_closes_the_dialog_and_toasts(client, kit_on):
    response = client.post("/_kit/demo/dialog/", headers={"HX-Request": "true"})
    assert response.status_code == 204
    assert json.loads(response["HX-Trigger"]) == {
        "toast": {"message": "Released ₱60,000.00 to 12 scholars", "tone": "success"},
        "closeDialog": {},
    }


def test_demo_bulk_counts_only_known_rows(client, kit_on):
    response = client.post(
        "/_kit/demo/bulk/",
        {"ids": ["1", "2", "999"], "action": "approve"},
        headers={"HX-Request": "true"},
    )
    assert json.loads(response["HX-Trigger"])["toast"] == {
        "message": "Approved 2 applications",
        "tone": "success",
    }
    nothing = client.post("/_kit/demo/bulk/", {"action": "approve"}, headers={"HX-Request": "true"})
    assert json.loads(nothing["HX-Trigger"])["toast"]["tone"] == "warning"


def test_demo_bulk_unknown_action_warns_about_the_action(client, kit_on):
    response = client.post(
        "/_kit/demo/bulk/", {"ids": ["1"], "action": "delete"}, headers={"HX-Request": "true"}
    )
    assert json.loads(response["HX-Trigger"])["toast"] == {
        "message": "Choose an action for the selected applications.",
        "tone": "warning",
    }


def test_demo_bulk_without_htmx_redirects_and_shows_a_toast(client, kit_on, vite_build):
    response = client.post("/_kit/demo/bulk/", {"ids": ["1"], "action": "approve"})
    assert response.status_code == 302
    assert response["Location"] == "/_kit/#overlays"
    page = client.get(response["Location"]).content.decode()
    assert "toast--success" in page
    assert "Approved 1 application" in page
    assert "Approved 1 applications" not in page


def table_fragment(client, query: str) -> str:
    response = client.get(
        f"/_kit/{query}", headers={"HX-Request": "true", "HX-Target": "scholars-table"}
    )
    body: str = response.content.decode()
    return body


def test_result_count_is_a_live_region_outside_the_swapped_table(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    count = '<p id="scholars-count" class="table-count" role="status">12 scholars</p>'
    assert count in body
    assert body.index(count) < body.index('<div id="scholars-table"')
    assert "hx-swap-oob" not in body


def test_table_swaps_send_the_count_out_of_band(client, kit_on, vite_build):
    body = table_fragment(client, "?q=shaw")
    assert '<p id="scholars-count" hx-swap-oob="innerHTML">1 scholar</p>' in body
    assert body.count('id="scholars-count"') == 1


def test_filter_form_carries_the_current_sort(client, kit_on, vite_build):
    form = '<form id="scholar-filters" class="filters"'
    hidden = '<input type="hidden" name="sort" value="-school" form="scholar-filters">'
    assert form in client.get("/_kit/").content.decode()
    assert hidden in client.get("/_kit/?sort=-school").content.decode()
    assert hidden in table_fragment(client, "?sort=-school&q=a")
    for query in ("", "?sort=__class__"):
        assert 'name="sort"' not in table_fragment(client, query)


def test_clear_filters_reloads_the_whole_page(client, kit_on, vite_build):
    body = table_fragment(client, "?q=nobody-has-this-name")
    assert re.search(r'<a class="btn btn--secondary" href="/_kit/#data" hx-boost="false">', body)
