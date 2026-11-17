import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl
import pytest
import time_machine
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.awards.exporting import HEADERS
from apps.awards.models import Award
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.files.policy import XLSX
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)
from apps.students.tests.factories import FullProfileFactory

pytestmark = pytest.mark.django_db

FORMULA = '=HYPERLINK("http://x","y")'


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


class World:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program = ProgramFactory.create(slug="tcu-ceaa")
        self.standard = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard", name="Standard"
        )
        self.merit = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="merit", name="Merit"
        )
        self.staff = MembershipFactory.create(program=self.program).user

    def scholar(self, first: str, last: str, **fields: Any) -> Award:
        claimed = fields.pop("claimed", False)
        profile = FullProfileFactory.create(
            first_name=first,
            last_name=last,
            middle_name="Dela",
            user=UserFactory.create(verified=True) if claimed else None,
        )
        return make_scholar(
            self.program,
            fields.pop("tier", self.standard),
            [self.previous],
            profile=profile,
            **fields,
        )

    def url(self, **params: str) -> str:
        base = reverse("scholars:export", kwargs={"program": self.program.slug})
        if not params:
            return base
        from urllib.parse import urlencode

        return f"{base}?{urlencode(params)}"


@pytest.fixture
def world(client) -> World:
    world = World()
    client.force_login(world.staff)
    return world


def csv_rows(response: Any) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_csv_rows_follow_filters(client, world: World):
    world.scholar("Ana", "Cruz", status=Award.Status.SUSPENDED, claimed=True)
    world.scholar("Ben", "Abad", status=Award.Status.SUSPENDED)
    world.scholar("Cy", "Bato", status=Award.Status.SUSPENDED, tier=world.merit)
    world.scholar("Di", "Dino")  # active
    response = client.get(world.url(status="suspended", tier="standard"))
    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0] == list(HEADERS)
    assert [row[:2] for row in rows[1:]] == [["Abad", "Ben"], ["Cruz", "Ana"]]
    abad = dict(zip(HEADERS, rows[1], strict=True))
    assert abad["Middle name"] == "Dela"
    assert abad["Tier"] == "standard"
    assert abad["Status"] == "Suspended"
    assert abad["Started"] == str(world.previous)
    assert abad["School"] == "Factory College"
    assert abad["Year level"] == "2"
    assert abad["GWA"] == "88.00"
    assert abad["Grading scale"] == "Percent (0-100)"
    assert abad["Units"] == "18"
    assert abad["Terms recorded"] == "1"
    assert abad["Account"] == "Not claimed"
    assert dict(zip(HEADERS, rows[2], strict=True))["Account"] == "Claimed"


def test_headers(client, world: World):
    world.scholar("Ana", "Cruz")
    response = client.get(world.url())
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == (
        'attachment; filename="scholars-tcu-ceaa-active-2026-11-17.csv"'
    )
    assert "no-store" in response["Cache-Control"]


def test_filename_follows_tab(client, world: World):
    response = client.get(world.url(status="suspended"))
    assert "scholars-tcu-ceaa-suspended-2026-11-17.csv" in response["Content-Disposition"]


def test_unknown_format_is_csv(client, world: World):
    response = client.get(world.url(format="pdf"))
    assert response["Content-Type"].startswith("text/csv")


def test_xlsx_download(client, world: World):
    world.scholar("Ana", "Cruz")
    response = client.get(world.url(format="xlsx"))
    assert response["Content-Type"] == XLSX
    assert response["Content-Disposition"].endswith('-2026-11-17.xlsx"')
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    assert values[0] == list(HEADERS)
    assert values[1][:2] == ["Cruz", "Ana"]
    gwa = values[1][HEADERS.index("GWA")]
    assert gwa == 88
    assert sheet.cell(row=2, column=HEADERS.index("GWA") + 1).data_type == "n"


def test_formula_name_neutralised_csv_and_xlsx(client, world: World):
    world.scholar("Ana", FORMULA)
    rows = csv_rows(client.get(world.url()))
    assert rows[1][0] == "'" + FORMULA
    response = client.get(world.url(format="xlsx"))
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    assert sheet["A2"].data_type == "s"
    assert sheet["A2"].value == "'" + FORMULA


def test_audit_without_search(client, world: World):
    world.scholar("Ana", "Pena")
    world.scholar("Ben", "Cruz")
    client.get(world.url(q="Pena"))
    event = AuditEvent.objects.get(action="scholars.exported")
    assert event.data == {"format": "csv", "status": "active", "tier": "", "rows": 1}
    assert event.program == world.program
    assert "Pena" not in str(event.data)


def test_other_program_rows_absent(client, world: World):
    other = ProgramFactory.create()
    other_tier = BenefitTierFactory.create(program=other, effective_from=world.previous)
    make_scholar(
        other,
        other_tier,
        [world.previous],
        profile=FullProfileFactory.create(last_name="Elsewhere"),
    )
    world.scholar("Ana", "Cruz")
    rows = csv_rows(client.get(world.url(status="all")))
    assert [row[0] for row in rows[1:]] == ["Cruz"]


def test_other_programs_staff_403(client, world: World):
    outsider = MembershipFactory.create().user
    client.force_login(outsider)
    assert client.get(world.url()).status_code == 403


def test_query_budget(client, world: World, django_assert_max_num_queries):
    for n in range(30):
        world.scholar(f"Name{n}", f"Last{n}")
    with django_assert_max_num_queries(10):
        response = client.get(world.url())
    assert len(csv_rows(response)) == 31


def test_empty_list_exports_headers(client, world: World):
    rows = csv_rows(client.get(world.url()))
    assert rows == [list(HEADERS)]


def test_list_has_export_links(client, world: World):
    world.scholar("Ana", "Cruz")
    list_url = reverse("scholars:list", kwargs={"program": world.program.slug})
    content = client.get(f"{list_url}?status=suspended&q=Ana&tier=standard").content.decode()
    assert "Export CSV" in content
    assert "Export XLSX" in content
    base = world.url()
    assert f"{base}?status=suspended&amp;q=Ana&amp;tier=standard&amp;format=csv" in content
    assert f"{base}?status=suspended&amp;q=Ana&amp;tier=standard&amp;format=xlsx" in content


def test_decimal_gwa_kept_exact_in_csv(client, world: World):
    world.scholar("Ana", "Cruz", gwa=Decimal("1.75"), gwa_scale="one_to_five")
    abad = dict(zip(HEADERS, csv_rows(client.get(world.url()))[1], strict=True))
    assert abad["GWA"] == "1.75"
    assert abad["Grading scale"] == "1.00 to 5.00 (1.00 highest)"
