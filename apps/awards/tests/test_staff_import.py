import html
import uuid
from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.awards.importing import ALREADY_IMPORTED, COLUMNS, TEMPLATE_CSV
from apps.awards.models import Award
from apps.awards.tabular import write_csv
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.policy import CSV
from apps.files.tests.factories import StoredFileFactory
from apps.files.views import UNAVAILABLE
from apps.programs.models import Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    SchoolFactory,
)

pytestmark = pytest.mark.django_db

HEADER = list(COLUMNS)


def row(**values: str) -> list[object]:
    base = {column: "" for column in COLUMNS}
    base.update(
        last_name="Santos",
        first_name="Felipe",
        birth_date="2005-03-14",
        tier="standard",
        school="Taguig City University",
    )
    base.update(values)
    return [base[column] for column in COLUMNS]


class World:
    def __init__(self) -> None:
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program = ProgramFactory.create(name="TCU CEAA")
        BenefitTierFactory.create(
            program=self.program, effective_from=self.current, code="standard"
        )
        SchoolFactory.create(name="Taguig City University", type="lcu", grading_scale="percent")
        self.staff = MembershipFactory.create(program=self.program).user
        self.bodies: dict[str, bytes] = {}

    def url(self) -> str:
        return reverse("scholars:import", kwargs={"program": self.program.slug})

    def file(self, rows: list[list[object]], header: list[str] | None = None) -> StoredFile:
        stored = StoredFileFactory.create(
            purpose=StoredFile.Purpose.IMPORT,
            status=StoredFile.Status.READY,
            declared_type=CSV,
            sniffed_type=CSV,
            sha256="0" * 64,
            uploaded_by=self.staff,
        )
        self.bodies[stored.key] = write_csv(header or HEADER, rows)
        return stored


@pytest.fixture
def world(client, monkeypatch) -> World:
    world = World()
    monkeypatch.setattr(storage, "read_all", lambda key: world.bodies[key])
    client.force_login(world.staff)
    return world


def page(response: Any) -> str:
    return html.unescape(response.content.decode())


def test_get_page(client, world: World):
    response = client.get(world.url())
    assert response.status_code == 200
    content = page(response)
    assert 'data-upload-purpose="import"' in content
    assert "Download the template" in content
    assert reverse("scholars:import-template", kwargs={"program": world.program.slug}) in content
    assert (
        "Every row must be a student who doesn't hold a TCU CEAA award yet, so an exported list "
        "can't be imported again."
    ) in content
    assert "Format the student number column as text so Excel keeps leading zeros." in content
    for column in COLUMNS:
        assert column in content


def test_template_download(client, world: World):
    response = client.get(
        reverse("scholars:import-template", kwargs={"program": world.program.slug})
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == (
        'attachment; filename="scholars-import-template.csv"'
    )
    assert "no-store" in response["Cache-Control"]
    assert response.content == TEMPLATE_CSV


def test_check_renders_preview(client, world: World):
    stored = world.file([row(), row(first_name="Lia", last_name="Reyes")])
    response = client.post(world.url(), {"action": "check", "file": str(stored.pk)})
    assert response.status_code == 200
    content = page(response)
    assert "2 scholars ready: 2 new students, 0 existing." in content
    assert "Felipe Santos" in content
    assert "14 March 2005" in content
    assert "New student" in content
    assert "Import 2 scholars" in content
    assert f'value="{stored.pk}"' in content


def test_check_with_errors(client, world: World):
    stored = world.file([row(), row(first_name="Lia", tier="premier")])
    response = client.post(world.url(), {"action": "check", "file": str(stored.pk)})
    assert response.status_code == 400
    content = page(response)
    assert "Fix the rows below, then upload the file again." in content
    assert "Tier: Use one of the tier codes in force for" in content
    assert "Import 2 scholars" not in content


def test_check_file_problem(client, world: World):
    stored = world.file([], header=[*HEADER, "birthdate"])
    response = client.post(world.url(), {"action": "check", "file": str(stored.pk)})
    assert response.status_code == 400
    assert 'Unknown column "birthdate".' in page(response)


def test_check_unknown_file(client, world: World):
    response = client.post(world.url(), {"action": "check", "file": str(uuid.uuid4())})
    assert response.status_code == 400
    assert "Upload the file again." in page(response)


def test_check_storage_down(client, world: World, monkeypatch):
    stored = world.file([row()])

    def down(key: str) -> bytes:
        raise storage.StorageUnavailable("down")

    monkeypatch.setattr(storage, "read_all", down)
    response = client.post(world.url(), {"action": "check", "file": str(stored.pk)})
    assert response.status_code == 503
    assert UNAVAILABLE in page(response)


def test_unknown_action_400(client, world: World):
    stored = world.file([row()])
    response = client.post(world.url(), {"action": "nope", "file": str(stored.pk)})
    assert response.status_code == 400


def test_import_success(client, world: World):
    stored = world.file([row(), row(first_name="Lia", last_name="Reyes")])
    response = client.post(world.url(), {"action": "import", "file": str(stored.pk)})
    assert response.status_code == 302
    assert response["Location"] == reverse("scholars:list", kwargs={"program": world.program.slug})
    assert [str(m) for m in get_messages(response.wsgi_request)] == ["Imported 2 scholars."]
    assert Award.objects.filter(source="imported").count() == 2


def test_import_rejected(client, world: World):
    stored = world.file([row(tier="premier")])
    response = client.post(world.url(), {"action": "import", "file": str(stored.pk)})
    assert response.status_code == 400
    assert "Fix the rows below, then upload the file again." in page(response)
    assert not Award.objects.exists()


def test_import_twice(client, world: World):
    stored = world.file([row()])
    client.post(world.url(), {"action": "import", "file": str(stored.pk)})
    response = client.post(world.url(), {"action": "import", "file": str(stored.pk)})
    assert response.status_code == 302
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Imported 1 scholar.",
        ALREADY_IMPORTED,
    ]
    assert Award.objects.count() == 1


def test_import_unknown_file(client, world: World):
    response = client.post(world.url(), {"action": "import", "file": str(uuid.uuid4())})
    assert response.status_code == 400
    assert "Upload the file again." in page(response)


def test_inactive_program_404(client, world: World):
    stored = world.file([row()])
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    response = client.post(world.url(), {"action": "import", "file": str(stored.pk)})
    assert response.status_code == 404
    assert not Award.objects.exists()


def test_list_has_import_button(client, world: World):
    content = client.get(
        reverse("scholars:list", kwargs={"program": world.program.slug})
    ).content.decode()
    assert world.url() in content
    assert ">Import<" in content or "Import</a>" in content
