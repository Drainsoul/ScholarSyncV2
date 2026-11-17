"""Add scholar, import and export, end to end (M9b)."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.awards.exporting import HEADERS
from apps.awards.importing import COLUMNS
from apps.awards.tabular import write_csv
from apps.awards.tests.scholars import make_scholar
from apps.programs.models import BenefitTier, Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    SchoolFactory,
)
from apps.students.tests.factories import FullProfileFactory
from tests.e2e.flows import log_in, payload

pytestmark = pytest.mark.e2e

SLUG = "tcu-ceaa"


class World:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program: Program = ProgramFactory.create(slug=SLUG, name="TCU CEAA")
        self.tier: BenefitTier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard", name="Standard"
        )
        SchoolFactory.create(name="Taguig City University", type="lcu", grading_scale="percent")
        self.staff: User = MembershipFactory.create(program=self.program, user__verified=True).user


def import_csv(*rows: dict[str, str], header: list[str] | None = None) -> bytes:
    def values(row: dict[str, str]) -> list[object]:
        base = {column: "" for column in COLUMNS}
        base.update(birth_date="2005-03-14", tier="standard", school="Taguig City University")
        base.update(row)
        return [base[column] for column in COLUMNS]

    return write_csv(header or list(COLUMNS), [values(row) for row in rows])


def upload(page: Page, name: str, mime_type: str, body: bytes) -> None:
    field = page.locator(".file-input")
    field.locator("input[type=file]").set_input_files(files=payload(name, mime_type, body))
    expect(field.locator(".file-input__status")).to_have_text(f"{name} uploaded")


def test_staff_import_a_csv_with_no_browser_type(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    world = World()
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/")
    page.get_by_role("link", name="Import").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Import scholars")
    body = import_csv(
        {"first_name": "Lia", "last_name": "Peña"},
        {"first_name": "Ramon", "last_name": "Reyes"},
    )
    upload(page, "scholars.csv", "", body)  # some browsers give a .csv no type at all
    page.get_by_role("button", name="Check file").click()
    expect(page.get_by_text("2 scholars ready: 2 new students, 0 existing.")).to_be_visible()
    page.get_by_role("button", name="Import 2 scholars").click()
    expect(page.get_by_text("Imported 2 scholars.").first).to_be_visible()
    table = page.locator("table")
    expect(table.get_by_text("Lia Peña")).to_be_visible()
    expect(table.get_by_text("Ramon Reyes")).to_be_visible()
    assert console_errors == []


def test_excel_csv_type_reaches_the_preview(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    world = World()
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/import/")
    body = import_csv({"first_name": "Lia", "last_name": "Santos"})
    upload(page, "scholars.csv", "application/vnd.ms-excel", body)
    page.get_by_role("button", name="Check file").click()
    expect(page.get_by_text("1 scholar ready: 1 new student, 0 existing.")).to_be_visible()
    assert console_errors == []


def test_a_bad_file_shows_the_problem_and_no_import(
    page: Page, live_server, vite_build, e2e_storage
):
    world = World()
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/import/")
    body = import_csv({"first_name": "Lia"}, header=[*COLUMNS, "birthdate"])
    upload(page, "scholars.csv", "text/csv", body)
    page.get_by_role("button", name="Check file").click()
    expect(page.get_by_text('Unknown column "birthdate".', exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Import 1 scholar")).to_have_count(0)


def test_staff_add_a_scholar_by_hand(page: Page, live_server, vite_build, console_errors):
    world = World()
    FullProfileFactory.create(
        user=None,
        first_name="Felipe",
        last_name="Santos",
        created_for=world.program,
        created_by=world.staff,
    )
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/")
    page.get_by_role("link", name="Add scholar").click()
    page.get_by_role("link", name="Choose Felipe Santos").click()
    page.get_by_label("School name").fill("Walk-in College")
    page.get_by_label("School type").select_option("private")
    page.get_by_label("Grading scale").select_option("percent")
    page.get_by_label("GWA").fill("88.50")
    page.get_by_role("button", name="Add scholar").click()
    expect(page.get_by_text("Added Felipe Santos as a scholar.").first).to_be_visible()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Felipe Santos")
    assert console_errors == []


def test_staff_export_the_list_as_csv(page: Page, live_server, vite_build, console_errors):
    world = World()
    make_scholar(
        world.program,
        world.tier,
        [world.previous],
        profile=FullProfileFactory.create(first_name="Ana", last_name="Cruz"),
    )
    log_in(page, live_server.url, world.staff.email, f"/staff/{SLUG}/scholars/")
    with page.expect_download() as info:
        page.get_by_role("link", name="Export CSV").click()
    download = info.value
    assert download.suggested_filename.startswith(f"scholars-{SLUG}-active-")
    lines = Path(download.path()).read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == ",".join(HEADERS)
    assert lines[1].startswith("Cruz,Ana,")
    assert console_errors == []
