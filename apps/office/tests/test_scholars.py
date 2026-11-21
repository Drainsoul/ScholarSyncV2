"""Scholars across programs (M11c)."""

import csv
import io
from typing import Any

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.awards.models import Award
from apps.awards.tests.factories import AwardFactory
from apps.core.models import AuditEvent
from apps.programs.models import Program
from apps.programs.tests.factories import ProgramFactory
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

LIST = "/office/scholars/"
EXPORT = "/office/scholars/export/"


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _award(program: Program, first: str, last: str, **kwargs: Any) -> Award:
    profile = kwargs.pop("profile", None) or ProfileFactory.create(first_name=first, last_name=last)
    return AwardFactory.create(
        source_application__program=program, source_application__profile=profile, **kwargs
    )


def test_tabs_search_and_program_filter(client: Any, office: User) -> None:
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    _award(tcu, "Ana", "Reyes")
    _award(lani, "Ben", "Cruz")
    _award(lani, "Cara", "Lim", status=Award.Status.GRADUATED)
    html = client.get(LIST).content.decode()
    assert "Ana Reyes" in html and "Ben Cruz" in html and "Cara Lim" not in html
    assert "Cara Lim" in client.get(LIST + "?status=graduated").content.decode()
    html = client.get(LIST + f"?program={lani.pk}").content.decode()
    assert "Ben Cruz" in html and "Ana Reyes" not in html
    html = client.get(LIST + "?q=reyes").content.decode()
    assert "Ana Reyes" in html and "Ben Cruz" not in html
    fallback = client.get(LIST + "?status=nope&program=abc&page=zz")
    assert fallback.status_code == 200
    assert "Ana Reyes" in fallback.content.decode()


def test_two_programs_tab_is_gone_and_falls_back(client: Any, office: User) -> None:
    """One scholarship at a time (rev 33): the "In two or more programs" tab is removed, and its
    old link shows the default tab."""
    tcu = ProgramFactory.create(name="TCU CEAA")
    _award(tcu, "Eli", "Torres")
    _award(tcu, "Cara", "Lim", status=Award.Status.GRADUATED)
    html = client.get(LIST).content.decode()
    assert "In two or more programs" not in html
    response = client.get(LIST + "?status=multi")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Eli Torres" in html and "Cara Lim" not in html
    assert "In two or more programs" not in html


def test_other_programs_column(client: Any, office: User) -> None:
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    both = ProfileFactory.create(first_name="Dina", last_name="Santos")
    _award(tcu, "", "", profile=both)
    _award(lani, "", "", profile=both)
    response = client.get(LIST + f"?program={tcu.pk}")
    row = response.context["rows"][0]
    assert row["award"].other_programs == "LANI"


def test_inactive_program_row_has_no_link(client: Any, office: User) -> None:
    closed = ProgramFactory.create(name="Old Grant", is_active=False)
    award = _award(closed, "Fe", "Ramos")
    html = client.get(LIST).content.decode()
    assert "Fe Ramos" in html
    assert "Program closed" in html
    assert reverse("scholars:detail", kwargs={"program": closed.slug, "pk": award.pk}) not in html
    open_program = ProgramFactory.create(name="LANI")
    linked = _award(open_program, "Gil", "Uy")
    html = client.get(LIST).content.decode()
    assert (
        reverse("scholars:detail", kwargs={"program": open_program.slug, "pk": linked.pk}) in html
    )


def test_query_count_with_50_awards_in_3_programs(
    client: Any, office: User, django_assert_max_num_queries: Any
) -> None:
    programs = ProgramFactory.create_batch(3)
    for n in range(50):
        _award(programs[n % 3], f"First{n}", f"Last{n}")
    with django_assert_max_num_queries(14):
        assert client.get(LIST).status_code == 200


def test_export_csv_and_xlsx_headers_rows_and_audit(client: Any, office: User) -> None:
    tcu = ProgramFactory.create(name="TCU CEAA")
    _award(tcu, "=SUM(A1)", "Reyes")
    response = client.get(EXPORT + f"?format=csv&q=reyes&program={tcu.pk}")
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Disposition"].startswith('attachment; filename="scholars-all-active-')
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Program", "Last name", "First name"]
    assert rows[1][0] == "TCU CEAA"
    assert rows[1][2] == "'=SUM(A1)"
    event = AuditEvent.objects.get(action="scholars.exported")
    assert event.data == {
        "scope": "office",
        "format": "csv",
        "status": "active",
        "program": str(tcu.pk),
        "rows": 1,
    }
    assert "reyes" not in str(event.data).lower()
    response = client.get(EXPORT + "?format=xlsx")
    sheet = load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    assert sheet.cell(row=1, column=1).value == "Program"
    assert sheet.cell(row=2, column=1).value == "TCU CEAA"
