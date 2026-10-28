import re

import pytest

from apps.kit.views import LAYOUTS, MOCKUPS, icon_names


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_mockup_renders_with_one_h1(client, kit_on, vite_build, slug):
    response = client.get(f"/_kit/mockups/{slug}/")
    body = response.content.decode()
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert body.count("<h1") == 1
    assert body.count('<main id="main"') == 1


def test_unknown_mockup_is_404(client, kit_on, vite_build):
    assert client.get("/_kit/mockups/nope/").status_code == 404


def test_mockup_index_links_every_mockup(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/").content.decode()
    for slug in MOCKUPS:
        assert f'href="/_kit/mockups/{slug}/"' in body


def test_kit_pages_only_use_icons_in_the_sprite(client, kit_on, vite_build):
    urls = ["/_kit/", "/_kit/mockups/"]
    urls += [f"/_kit/layouts/{name}/" for name in LAYOUTS]
    urls += [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]
    known = set(icon_names())
    for url in urls:
        used = set(re.findall(r'icons\.svg#([a-z0-9-]+)"', client.get(url).content.decode()))
        assert used <= known, (url, used - known)
