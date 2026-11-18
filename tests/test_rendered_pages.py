"""Every page, as every persona, is clean under the enforced CSP (M12).

The template-source scan (`apps/core/tests/test_templates.py`) can't see what tags and includes
render; this renders every GET route over a seeded world and checks the HTML itself."""

from html.parser import HTMLParser
from typing import Any

import pytest
from django.urls import NoReverseMatch, reverse

from tests.test_permission_matrix import PERSONAS, URL_KWARGS, URLS
from tests.test_permission_matrix import personas as personas  # noqa: F401 - the fixture
from tests.worlds import build_world

DATA_SCRIPT_TYPES = {"application/json", "application/ld+json"}
# Routes that only redirect or answer for an external provider: nothing to render.
SKIP = {"account_logout"}


class _Scanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: (value or "") for name, value in attrs}
        snippet = self.get_starttag_text() or f"<{tag}>"
        if tag == "script" and "src" not in values:
            if values.get("type", "").lower() not in DATA_SCRIPT_TYPES:
                self.problems.append(f"inline script: {snippet[:120]}")
        if tag == "style":
            self.problems.append(f"style element: {snippet[:120]}")
        for name, value in values.items():
            if name == "style":
                self.problems.append(f"style attribute: {snippet[:120]}")
            elif name.startswith("on"):
                self.problems.append(f"{name} handler: {snippet[:120]}")
            elif name in {
                "href",
                "src",
                "action",
                "formaction",
            } and value.strip().lower().startswith("javascript:"):
                self.problems.append(f"javascript: URL: {snippet[:120]}")


def rendered_problems(html: str) -> list[str]:
    """Inline scripts, style elements and attributes, event handlers and javascript: URLs."""
    scanner = _Scanner()
    scanner.feed(html)
    scanner.close()
    return scanner.problems


def test_rendered_problems_finds_each_kind() -> None:
    page = (
        "<script>alert(1)</script>"
        '<script type="application/json">{"a": 1}</script>'
        '<script src="/static/app.js"></script>'
        "<style>p{}</style>"
        '<p style="color:red">x</p>'
        '<button onclick="go()">x</button>'
        '<a href="javascript:void(0)">x</a>'
    )
    kinds = [problem.split(":")[0] for problem in rendered_problems(page)]
    assert kinds == [
        "inline script",
        "style element",
        "style attribute",
        "onclick handler",
        "javascript",
    ]
    assert rendered_problems('<main><a href="/x">x</a><script src="/a.js"></script></main>') == []


@pytest.mark.parametrize("persona", PERSONAS)
def test_every_get_page_is_csp_clean(
    persona: str, client: Any, personas: dict[str, Any], vite_build: Any
) -> None:
    kwargs = {**URL_KWARGS, **build_world(personas)}
    user = personas[persona]
    if user is not None:
        client.force_login(user)
    problems: list[str] = []
    rendered = 0
    for name in sorted(URLS):
        if name in SKIP:
            continue
        try:
            url = reverse(name, kwargs=kwargs.get(name))
        except NoReverseMatch:
            continue
        response = client.get(url)
        if response.status_code != 200 or not response.get("Content-Type", "").startswith(
            "text/html"
        ):
            continue
        rendered += 1
        problems += [
            f"{name} as {persona}: {problem}"
            for problem in rendered_problems(response.content.decode())
        ]
    assert rendered > 0
    assert problems == []


def test_detail_pages_render_from_the_world(client: Any, personas: dict[str, Any]) -> None:
    """The scan reaches detail pages, not only the matrix's 404s."""
    world = build_world(personas)
    client.force_login(personas["staff"])
    for name in (
        "review:detail",
        "scholars:detail",
        "reports:detail",
        "money:schedule",
        "workspace:task-edit",
        "review:behalf",
    ):
        assert client.get(reverse(name, kwargs=world[name])).status_code == 200, name
    client.force_login(personas["office"])
    for name in (
        "office:report-detail",
        "office:staff-detail",
        "office:school-edit",
        "settings:tier-change",
        "settings:document-edit",
    ):
        assert client.get(reverse(name, kwargs=world[name])).status_code == 200, name
    client.force_login(personas["student"])
    for name in (
        "applications:detail",
        "students:profile-family-edit",
        "students:profile-education-edit",
    ):
        assert client.get(reverse(name, kwargs=world[name])).status_code == 200, name
