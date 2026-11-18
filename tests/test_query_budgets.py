"""Every page stays within a query budget, whatever the number of rows (M12, spec §13).

Each GET route renders as each persona that gets a 200, over a world with 30 of each listed
thing; a page whose query count grows with rows (an N+1) fails here."""

from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from tests.test_permission_matrix import PERSONAS, URL_KWARGS, URLS
from tests.test_permission_matrix import personas as personas  # noqa: F401 - the fixture
from tests.worlds import build_world

ROWS = 30
CEILING = 25
# URL name -> its own ceiling, each with the reason.
EXCEPTIONS: dict[str, int] = {}
SKIP = {"account_logout"}


@pytest.mark.parametrize("persona", PERSONAS)
def test_every_page_stays_within_its_query_budget(
    persona: str, client: Any, personas: dict[str, Any], vite_build: Any
) -> None:
    kwargs = {**URL_KWARGS, **build_world(personas, rows=ROWS)}
    user = personas[persona]
    if user is not None:
        client.force_login(user)
    over: list[str] = []
    for name in sorted(URLS):
        if name in SKIP:
            continue
        try:
            url = reverse(name, kwargs=kwargs.get(name))
        except NoReverseMatch:
            continue
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
        if response.status_code != 200:
            continue
        ceiling = EXCEPTIONS.get(name, CEILING)
        if len(queries) > ceiling:
            over.append(f"{name} ({persona}): {len(queries)} queries (ceiling {ceiling})")
    assert over == [], "\n".join(over)


def test_world_fills_the_lists(client: Any, personas: dict[str, Any], vite_build: Any) -> None:
    """The budget measures full pages: the lists hold a page's worth of rows."""
    build_world(personas, rows=ROWS)
    client.force_login(personas["staff"])
    queue = client.get("/staff/tcu-ceaa/applications/?status=all").content.decode()
    assert queue.count('href="/staff/tcu-ceaa/applications/') >= 25
    scholars = client.get("/staff/tcu-ceaa/scholars/").content.decode()
    assert scholars.count("scholar=") >= 25
    client.force_login(personas["office"])
    audit = client.get("/office/audit/").content.decode()
    assert audit.count("Added a scholar") >= 25
    reports = client.get("/office/reports/").content.decode()
    assert reports.count('href="/office/reports/') >= 25
