import threading
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse

from apps.awards import importing, services
from apps.awards.importing import (
    ALREADY_IMPORTED,
    BAD_DATE,
    COLUMNS,
    DUPLICATE_ROW,
    MANY_MATCHES,
    MISSING_COLUMNS,
    NO_ROWS,
    NO_SUCH_TERM,
    TEMPLATE_CSV,
    TERM_PAIR,
    UNKNOWN_COLUMN,
    ImportPreview,
    ImportRejected,
    check_import,
    import_scholars,
)
from apps.awards.models import Award, ScholarImport, ScholarTerm
from apps.awards.services import FUTURE_TERM, _record_values, already_holds
from apps.awards.tabular import write_csv
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.policy import CSV
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    SchoolFactory,
)
from apps.students.models import ProfileInvite, StudentProfile
from apps.students.tests.factories import FullProfileFactory, ProfileFactory

pytestmark = pytest.mark.django_db

HEADER = list(COLUMNS)


def row(**values: Any) -> list[object]:
    base: dict[str, object] = {
        "last_name": "Santos",
        "first_name": "Felipe",
        "middle_name": "",
        "suffix": "",
        "birth_date": "2005-03-14",
        "student_number": "",
        "tier": "standard",
        "school_year": "",
        "term": "",
        "school": "Taguig City University",
        "school_type": "",
        "gwa_scale": "",
        "course": "BSED",
        "year_level": "1",
        "gwa": "88.50",
        "units": "21",
    }
    base.update(values)
    return [base[column] for column in HEADER]


class World:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program = ProgramFactory.create()
        self.tier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard"
        )
        BenefitTierFactory.create(program=self.program, effective_from=self.previous, code="merit")
        self.tcu = SchoolFactory.create(
            name="Taguig City University", type="lcu", grading_scale="percent"
        )
        self.staff = MembershipFactory.create(program=self.program).user
        self.bodies: dict[str, bytes] = {}

    def file(self, rows: list[list[object]], header: list[str] | None = None) -> StoredFile:
        stored = StoredFileFactory.create(
            purpose=StoredFile.Purpose.IMPORT,
            status=StoredFile.Status.READY,
            declared_type=CSV,
            sniffed_type=CSV,
            sha256="0" * 64,
            uploaded_by=self.staff,
            original_name="scholars.csv",
        )
        self.bodies[stored.key] = write_csv(header or HEADER, rows)
        return stored

    def check(self, rows: list[list[object]], header: list[str] | None = None) -> ImportPreview:
        return check_import(self.program, self.file(rows, header))

    def known(self, first: str = "Ana", last: str = "Cruz", **fields: Any) -> StudentProfile:
        return FullProfileFactory.create(
            user=None,
            first_name=first,
            last_name=last,
            birth_date=date(2005, 3, 14),
            created_for=self.program,
            **fields,
        )

    def run(self, stored: StoredFile, **kwargs: Any) -> ScholarImport:
        return import_scholars(
            actor=kwargs.pop("actor", self.staff),
            program=self.program,
            file_id=stored.pk,
            **kwargs,
        )


@pytest.fixture
def world(monkeypatch) -> World:
    world = World()
    monkeypatch.setattr(storage, "read_all", lambda key: world.bodies[key])
    return world


def test_template_is_the_header():
    assert TEMPLATE_CSV.decode("utf-8-sig").strip() == ",".join(COLUMNS)


def test_valid_file_previews_ok(world: World):
    world.known()
    preview = world.check(
        [row(), row(first_name="Ana", last_name="Cruz"), row(first_name="Lia", last_name="Reyes")]
    )
    assert preview.problem == ""
    assert preview.ok
    assert (preview.new_count, preview.matched_count) == (2, 1)
    first = preview.rows[0]
    assert (first.line, first.name, first.birth_date) == (2, "Felipe Santos", date(2005, 3, 14))
    assert first.term_label == str(world.current)
    assert (first.tier_code, first.school, first.errors) == (
        "standard",
        "Taguig City University",
        [],
    )
    assert first.is_new
    assert not preview.rows[1].is_new


def test_blank_term_is_current(world: World):
    preview = world.check([row()])
    data = preview.rows[0].data
    assert data is not None
    assert data.record.term == world.current


def test_named_term(world: World):
    for year, term in [("2025-2026", "2"), ("2025", "2nd semester"), ("2025", "2nd Semester")]:
        data = world.check([row(school_year=year, term=term)]).rows[0].data
        assert data is not None
        assert data.record.term == world.previous


def test_listed_school_by_name(world: World):
    data = world.check([row(school="taguig city university")]).rows[0].data
    assert data is not None
    assert (data.record.school, data.record.school_name) == (world.tcu, "")
    # A listed school supplies its scale when the record is written.
    assert _record_values(data.record)["gwa_scale"] == "percent"


def test_unlisted_school_needs_type_and_scale(world: World):
    preview = world.check([row(school="Faraway College")])
    assert not preview.ok
    assert "School type: This field is required." in preview.rows[0].errors
    assert "Grading scale: This field is required." in preview.rows[0].errors


def test_type_and_scale_by_label(world: World):
    preview = world.check(
        [
            row(
                school="Faraway College",
                school_type="State university or college",
                gwa_scale="Percent (0-100)",
            )
        ]
    )
    data = preview.rows[0].data
    assert data is not None
    assert (data.record.school_name, data.record.school_type, data.record.gwa_scale) == (
        "Faraway College",
        "suc",
        "percent",
    )


def test_xlsx_style_values(world: World):
    preview = world.check(
        [
            row(
                birth_date=date(2005, 3, 14),
                gwa="1.75",
                school="Up Diliman",
                school_type="suc",
                gwa_scale="one_to_five",
            )
        ]
    )
    data = preview.rows[0].data
    assert data is not None
    assert data.record.gwa == Decimal("1.75")


def test_missing_columns(world: World):
    header = [c for c in HEADER if c not in ("birth_date", "tier")]
    preview = world.check([], header=header)
    assert preview.problem == MISSING_COLUMNS.format(columns="birth_date, tier")
    assert not preview.ok


def test_unknown_column(world: World):
    preview = world.check([], header=[*HEADER, "birthdate"])
    assert preview.problem == UNKNOWN_COLUMN.format(column="birthdate")


def test_table_error_is_problem(world: World):
    stored = world.file([])
    world.bodies[stored.key] = b"last_name\n\x81\x8d\n"
    preview = check_import(world.program, stored)
    assert preview.problem == (
        "We couldn't read this file's text. Save it as CSV UTF-8 and try again."
    )


def test_empty_file(world: World):
    assert world.check([]).problem == NO_ROWS


def test_duplicate_in_file(world: World):
    preview = world.check([row(), row(first_name=" felipe ", last_name="SANTOS")])
    assert preview.rows[0].errors == []
    assert preview.rows[1].errors == [DUPLICATE_ROW.format(line=2)]
    assert not preview.ok


def test_many_matches(world: World):
    world.known("Felipe", "Santos")
    world.known("Felipe", "Santos")
    preview = world.check([row()])
    assert preview.rows[0].errors == [MANY_MATCHES]


def test_holder_row(world: World):
    profile = world.known("Felipe", "Santos")
    make_scholar(world.program, world.tier, [world.previous], profile=profile)
    preview = world.check([row()])
    assert preview.rows[0].errors == [already_holds(world.program)]


ONE_AT_A_TIME = (
    "This student already holds the LANI scholarship. A student can hold one scholarship at a time."
)


def hold_elsewhere(world: World, profile: StudentProfile, status: str = "active") -> Award:
    lani = ProgramFactory.create(name="LANI")
    tier = BenefitTierFactory.create(program=lani, effective_from=world.previous)
    return make_scholar(lani, tier, [world.previous], profile=profile, status=status)


@pytest.mark.parametrize("status", ["active", "suspended"])
def test_row_holding_another_programs_award(world: World, status: str):
    hold_elsewhere(world, world.known("Felipe", "Santos"), status)
    preview = world.check([row()])
    assert preview.rows[0].errors == [ONE_AT_A_TIME]
    assert not preview.ok


def test_row_with_an_ended_award_elsewhere_passes(world: World):
    hold_elsewhere(world, world.known("Felipe", "Santos"), "graduated")
    assert world.check([row()]).ok


def test_unknown_term(world: World):
    preview = world.check([row(school_year="2019-2020", term="1")])
    assert preview.rows[0].errors == [NO_SUCH_TERM.format(label="1st semester, SY 2019–2020")]


def test_future_term(world: World):
    AcademicTermFactory.create(school_year_start=2026, term=2)
    preview = world.check([row(school_year="2026", term="2")])
    assert preview.rows[0].errors == [FUTURE_TERM]


def test_term_pair(world: World):
    preview = world.check([row(school_year="2026", term="")])
    assert preview.rows[0].errors == [TERM_PAIR]


def test_bad_term_words(world: World):
    preview = world.check([row(school_year="next year", term="fall")])
    assert preview.rows[0].errors == [importing.BAD_TERM]


def test_bad_date(world: World):
    preview = world.check([row(birth_date="14/03/2005")])
    assert preview.rows[0].errors == [f"Birth date: {BAD_DATE}"]


def test_us_date(world: World):
    preview = world.check([row(birth_date="3/14/2005")])
    assert preview.rows[0].birth_date == date(2005, 3, 14)
    assert preview.ok


def test_bad_tier(world: World):
    preview = world.check([row(tier="premier")])
    assert preview.rows[0].errors == [
        f"Tier: Use one of the tier codes in force for {world.current}: merit, standard."
    ]


def test_required_name(world: World):
    preview = world.check([row(last_name="")])
    assert "Last name: This field is required." in preview.rows[0].errors


def test_self_registered_not_matched(world: World):
    ProfileFactory.create(first_name="Felipe", last_name="Santos", birth_date=date(2005, 3, 14))
    preview = world.check([row()])
    assert preview.ok
    assert preview.rows[0].is_new


def test_preview_query_budget(world: World, django_assert_max_num_queries):
    for n in range(10):
        world.known(f"Known{n}", "Cruz")
    stored = world.file(
        [row(first_name=f"Known{n}", last_name="Cruz") for n in range(10)]
        + [row(first_name=f"New{n}") for n in range(40)]
    )
    with django_assert_max_num_queries(12):
        preview = check_import(world.program, stored)
    assert preview.ok
    assert len(preview.rows) == 50


def test_import_commits_all(world: World):
    world.known()
    stored = world.file(
        [row(), row(first_name="Ana", last_name="Cruz"), row(first_name="Lia", last_name="Reyes")]
    )
    batch = world.run(stored)
    assert batch.row_count == 3
    assert (batch.program, batch.file, batch.imported_by) == (world.program, stored, world.staff)
    awards = list(Award.objects.order_by("pk"))
    assert len(awards) == 3
    assert {a.source for a in awards} == {"imported"}
    assert {a.import_batch_id for a in awards} == {batch.pk}
    assert ScholarTerm.objects.count() == 3
    new = StudentProfile.objects.filter(first_name__in=["Felipe", "Lia"])
    assert {(p.created_for, p.created_by, p.user) for p in new} == {
        (world.program, world.staff, None)
    }
    assert not ProfileInvite.objects.exists()
    imported = list(AuditEvent.objects.filter(action="profile.imported"))
    assert len(imported) == 2
    assert all(e.data == {} and e.program == world.program for e in imported)
    assert AuditEvent.objects.filter(action="award.created").count() == 3
    event = AuditEvent.objects.get(action="scholars.imported")
    assert event.data == {"file": str(stored.pk), "rows": 3, "new_profiles": 2}
    assert event.program == world.program


def test_import_rejects_when_any_row_fails(world: World):
    stored = world.file([row(), row(first_name="Lia", tier="premier")])
    with pytest.raises(ImportRejected) as caught:
        world.run(stored)
    assert caught.value.preview.rows[1].errors
    assert not Award.objects.exists()
    assert not StudentProfile.objects.filter(first_name="Felipe").exists()
    assert not ScholarImport.objects.exists()


def test_import_twice(world: World):
    stored = world.file([row()])
    world.run(stored)
    with pytest.raises(ValidationError) as caught:
        world.run(stored)
    assert caught.value.messages == [ALREADY_IMPORTED]
    assert Award.objects.count() == 1


def test_import_revalidates(world: World, monkeypatch):
    profile = world.known("Felipe", "Santos")
    stored = world.file([row()])
    assert check_import(world.program, stored).ok
    make_scholar(world.program, world.tier, [world.previous], profile=profile)
    with pytest.raises(ImportRejected) as caught:
        world.run(stored)
    assert caught.value.preview.rows[0].errors == [already_holds(world.program)]
    assert Award.objects.count() == 1


def test_import_refuses_a_row_that_gained_an_award_elsewhere(world: World):
    profile = world.known("Felipe", "Santos")
    stored = world.file([row(), row(first_name="Lia")])
    assert check_import(world.program, stored).ok
    hold_elsewhere(world, profile)
    with pytest.raises(ImportRejected) as caught:
        world.run(stored)
    assert caught.value.preview.rows[0].errors == [ONE_AT_A_TIME]
    assert not Award.objects.filter(program=world.program).exists()
    assert not ScholarImport.objects.exists()


def test_import_commit_refuses_under_the_lock(world: World, monkeypatch):
    """The award lands after the commit's own preview: create_award refuses under the lock."""
    profile = world.known("Felipe", "Santos")
    stored = world.file([row()])
    real = importing.check_import

    def then_award(program: Any, file: Any) -> Any:
        preview = real(program, file)
        hold_elsewhere(world, profile)
        return preview

    monkeypatch.setattr(importing, "check_import", then_award)
    with pytest.raises(ImportRejected) as caught:
        world.run(stored)
    assert caught.value.preview.rows[0].errors == [ONE_AT_A_TIME]
    assert not Award.objects.filter(program=world.program).exists()


def test_create_award_refusal_rolls_back(world: World, monkeypatch):
    stored = world.file([row(), row(first_name="Lia")])
    real = services.create_award
    calls: list[int] = []

    def flaky(**kwargs: Any) -> Award:
        calls.append(1)
        if len(calls) == 2:
            raise ValidationError(already_holds(world.program))
        return real(**kwargs)

    monkeypatch.setattr("apps.awards.importing.create_award", flaky)
    with pytest.raises(ImportRejected) as caught:
        world.run(stored)
    assert caught.value.preview.rows[1].errors == [already_holds(world.program)]
    assert not Award.objects.exists()
    assert not ScholarImport.objects.exists()


def test_import_other_users_file_404(world: World):
    stored = world.file([row()])
    other = MembershipFactory.create(program=world.program).user
    with pytest.raises(Http404):
        world.run(stored, actor=other)
    with pytest.raises(Http404):
        import_scholars(actor=world.staff, program=world.program, file_id=uuid.uuid4())


def test_import_query_budget(world: World, django_assert_max_num_queries):
    stored = world.file([row(first_name=f"New{n}") for n in range(50)])
    # Per row: a profile insert + its audit, and create_award's checks, award, record and audit.
    with django_assert_max_num_queries(50 * 16 + 20):
        batch = world.run(stored)
    assert batch.row_count == 50


@pytest.mark.django_db(transaction=True)
def test_concurrent_import_creates_once(monkeypatch):
    world = World()
    monkeypatch.setattr(storage, "read_all", lambda key: world.bodies[key])
    stored = world.file([row()])
    errors: list[BaseException] = []

    def run() -> None:
        from django.db import connection

        try:
            world.run(stored)
        except ValidationError as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert Award.objects.count() == 1
    assert ScholarImport.objects.count() == 1
    assert [e.messages for e in errors if isinstance(e, ValidationError)] == [[ALREADY_IMPORTED]]


def test_imported_profile_on_students_page(world: World, client):
    world.run(world.file([row()]))
    profile = StudentProfile.objects.get(first_name="Felipe")
    client.force_login(world.staff)
    students = reverse("workspace:students", kwargs={"program": world.program.slug})
    page = client.get(students).content.decode()
    assert "Felipe Santos" in page
    assert "Not invited" in page
    invite = reverse(
        "workspace:students-invite",
        kwargs={"program": world.program.slug, "profile_id": profile.pk},
    )
    assert client.post(invite, {"email": "felipe@example.com"}).status_code == 302
    assert ProfileInvite.objects.get(profile=profile).email == "felipe@example.com"


@pytest.mark.django_db(transaction=True)
def test_concurrent_imports_of_different_files_create_one_person(monkeypatch):
    """Two files naming the same new person, imported at the same moment: one wins, the other is
    refused (the program lock serialises them), never two profiles each with an award."""
    world = World()
    monkeypatch.setattr(storage, "read_all", lambda key: world.bodies[key])
    first, second = world.file([row()]), world.file([row()])
    real_check = importing.check_import
    barrier = threading.Barrier(2, timeout=3)

    def overlapping_check(program: Any, file: StoredFile) -> ImportPreview:
        try:
            barrier.wait()  # without a lock both threads get here before either writes
        except threading.BrokenBarrierError:
            pass
        return real_check(program, file)

    monkeypatch.setattr("apps.awards.importing.check_import", overlapping_check)
    outcomes: list[str] = []

    def run(stored: StoredFile) -> None:
        from django.db import connection

        try:
            world.run(stored)
            outcomes.append("imported")
        except ImportRejected:
            outcomes.append("rejected")
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(f,)) for f in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert StudentProfile.objects.filter(first_name="Felipe", last_name="Santos").count() == 1
    assert Award.objects.count() == 1
    assert sorted(outcomes) == ["imported", "rejected"]


@pytest.mark.parametrize(
    ("birth", "message"),
    [
        ("2999-03-14", "Birth date: The birth date can't be in the future."),
        ("0205-03-14", "Birth date: Enter a birth date from 1900 onward."),
    ],
)
def test_birth_date_rules_match_the_hand_form(world: World, birth: str, message: str):
    preview = world.check([row(birth_date=birth)])
    assert preview.rows[0].errors == [message]
    assert not preview.ok
