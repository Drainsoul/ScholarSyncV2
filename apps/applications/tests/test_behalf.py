from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications import behalf
from apps.applications.behalf import (
    ACADEMICS_FROZEN,
    NO_TERM,
    STAFF_HELD,
    STAFF_REJECTED,
    STUDENT_OPEN,
    attach_on_behalf,
    set_academics,
    start_on_behalf,
    withdraw_on_behalf,
)
from apps.applications.models import Application, Document
from apps.applications.review_selectors import behalf_application
from apps.applications.selectors import open_application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.core.models import AuditEvent
from apps.files.models import StoredFile
from apps.files.policy import MB, PDF, PNG
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import AcademicTerm, Program, RequiredDocument, School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.students.models import StudentProfile
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

S = Application.Status


class World:
    def __init__(self) -> None:
        self.term: AcademicTerm = AcademicTermFactory.create(is_current=True)
        self.program: Program = ProgramFactory.create()
        self.actor: User = MembershipFactory.create(program=self.program).user
        self.profile: StudentProfile = ProfileFactory.create(created_for=self.program)


@pytest.fixture
def world() -> World:
    return World()


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


def start(world: World) -> Application:
    return start_on_behalf(actor=world.actor, program=world.program, profile_id=world.profile.pk)


def assert_refused(world: World, message: str) -> None:
    with pytest.raises(ValidationError) as caught:
        start(world)
    assert caught.value.messages == [message]
    assert actions() == []


def test_start_creates_on_behalf_draft(world: World) -> None:
    application = start(world)
    assert application.status == S.DRAFT
    assert application.on_behalf is True
    assert application.created_by == world.actor
    assert application.term == world.term
    assert application.profile == world.profile
    event = AuditEvent.objects.get()
    assert event.action == "application.started_on_behalf"
    assert event.target_id == str(application.pk)
    assert event.program == world.program
    assert event.data == {}


def test_start_twice_returns_the_same_draft(world: World) -> None:
    first = start(world)
    second = start(world)
    assert first.pk == second.pk
    assert Application.objects.count() == 1
    assert actions() == ["application.started_on_behalf"]


def test_start_refused_for_other_programs_profile(world: World) -> None:
    other = ProfileFactory.create(created_for=ProgramFactory.create())
    with pytest.raises(Http404):
        start_on_behalf(actor=world.actor, program=world.program, profile_id=other.pk)
    assert Application.objects.count() == 0
    assert actions() == []


def test_start_refused_for_inactive_program(world: World) -> None:
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    with pytest.raises(Http404):
        start(world)
    assert Application.objects.count() == 0


def test_start_refused_for_student_role(world: World) -> None:
    student = UserFactory.create()
    with pytest.raises(PermissionDenied):
        start_on_behalf(actor=student, program=world.program, profile_id=world.profile.pk)
    assert Application.objects.count() == 0


def test_start_refused_when_held(world: World) -> None:
    ApplicationFactory.create(
        profile=world.profile, program=world.program, term=world.term, status=S.APPROVED
    )
    assert_refused(world, STAFF_HELD)


def test_start_refused_when_rejected_this_term(world: World) -> None:
    ApplicationFactory.create(
        profile=world.profile, program=world.program, term=world.term, status=S.REJECTED
    )
    assert_refused(world, STAFF_REJECTED.format(term=world.term))


def test_start_refused_when_student_has_open_application(world: World) -> None:
    ApplicationFactory.create(profile=world.profile, program=world.program, term=world.term)
    assert_refused(world, STUDENT_OPEN.format(program=world.program.name))


def test_start_race_with_student_draft(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    ApplicationFactory.create(profile=world.profile, program=world.program, term=world.term)
    calls: list[int] = []

    def stale_then_real(*args: Any, **kwargs: Any) -> Application | None:
        calls.append(1)
        return None if len(calls) == 1 else open_application(*args, **kwargs)

    monkeypatch.setattr(behalf, "open_application", stale_then_real)
    assert_refused(world, STUDENT_OPEN.format(program=world.program.name))
    assert len(calls) == 2


def test_start_refused_without_current_term(world: World) -> None:
    AcademicTerm.objects.filter(pk=world.term.pk).update(
        is_current=False, starts_on=date(2020, 8, 1), ends_on=date(2020, 12, 1)
    )
    assert_refused(world, NO_TERM)


def test_withdraw_draft(world: World) -> None:
    application = start(world)
    withdrawn = withdraw_on_behalf(actor=world.actor, program=world.program, pk=application.pk)
    assert withdrawn.status == S.WITHDRAWN
    application.refresh_from_db()
    assert application.status == S.WITHDRAWN
    event = AuditEvent.objects.get(action="application.withdrawn")
    assert event.program == world.program
    assert event.target_id == str(application.pk)


def test_withdraw_returned(world: World) -> None:
    application = ApplicationFactory.create(
        profile=world.profile,
        program=world.program,
        term=world.term,
        status=S.RETURNED,
        on_behalf=True,
        created_by=world.actor,
    )
    withdraw_on_behalf(actor=world.actor, program=world.program, pk=application.pk)
    application.refresh_from_db()
    assert application.status == S.WITHDRAWN


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW])
def test_withdraw_submitted_refused(world: World, status: str) -> None:
    application = ApplicationFactory.create(
        profile=world.profile,
        program=world.program,
        term=world.term,
        status=status,
        on_behalf=True,
        created_by=world.actor,
    )
    with pytest.raises(ValidationError) as caught:
        withdraw_on_behalf(actor=world.actor, program=world.program, pk=application.pk)
    assert caught.value.messages == ["This application is with the reviewers now."]
    application.refresh_from_db()
    assert application.status == status
    assert actions() == []


def test_behalf_application_404_for_student_application_and_other_program(world: World) -> None:
    mine = ApplicationFactory.create(program=world.program, on_behalf=True)
    student = ApplicationFactory.create(program=world.program)
    foreign = ApplicationFactory.create(on_behalf=True)
    assert behalf_application(world.program, mine.pk).pk == mine.pk
    for pk in (student.pk, foreign.pk):
        with pytest.raises(Http404):
            behalf_application(world.program, pk)


WRITES = [withdraw_on_behalf, set_academics, attach_on_behalf]


@pytest.mark.parametrize("write", WRITES)
def test_writes_404_for_foreign_ids(world: World, write: Any) -> None:
    student = ApplicationFactory.create(program=world.program)
    foreign = ApplicationFactory.create(on_behalf=True)
    extra: dict[str, Any] = {}
    if write is set_academics:
        extra = {"data": {}}
    elif write is attach_on_behalf:
        extra = {
            "requirement": RequiredDocumentFactory.create(program=world.program),
            "file_id": staff_file(world.actor).pk,
        }
    for pk in (student.pk, foreign.pk):
        with pytest.raises(Http404):
            write(actor=world.actor, program=world.program, pk=pk, **extra)
    assert set(Application.objects.values_list("status", flat=True)) == {S.DRAFT}
    assert actions() == []


TYPED = {
    "school": None,
    "school_name": "Taguig Tech",
    "school_type": School.Type.PRIVATE,
    "gwa_scale": School.Scale.PERCENT,
    "course": "BS Biology",
    "year_level": 2,
    "gwa": Decimal("88.50"),
    "units": 21,
}


def draft(world: World, **kwargs: Any) -> Application:
    return ApplicationFactory.create(
        profile=world.profile,
        program=world.program,
        term=world.term,
        on_behalf=True,
        created_by=world.actor,
        **kwargs,
    )


def academics(world: World, application: Application, data: dict[str, Any]) -> Application:
    return set_academics(actor=world.actor, program=world.program, pk=application.pk, data=data)


def test_set_academics_on_draft(world: World) -> None:
    application = draft(world)
    academics(world, application, TYPED)
    application.refresh_from_db()
    assert application.school is None
    assert application.school_name == "Taguig Tech"
    assert application.school_type == School.Type.PRIVATE
    assert application.gwa_scale == School.Scale.PERCENT
    assert application.course == "BS Biology"
    assert application.year_level == 2
    assert application.gwa == Decimal("88.50")
    assert application.units == 21
    assert actions() == ["application.academics_set"]


def test_set_academics_listed_school_copies_type_and_scale(world: World) -> None:
    school = SchoolFactory.create(type=School.Type.PUBLIC, grading_scale=School.Scale.ONE_TO_FIVE)
    application = draft(world)
    data = {
        **TYPED,
        "school": school,
        "school_name": "Ignored",
        "school_type": School.Type.PRIVATE,
        "gwa_scale": School.Scale.PERCENT,
        "gwa": Decimal("1.75"),
    }
    academics(world, application, data)
    application.refresh_from_db()
    assert application.school == school
    assert application.school_name == ""
    assert application.school_type == School.Type.PUBLIC
    assert application.gwa_scale == School.Scale.ONE_TO_FIVE


@pytest.mark.parametrize("status", [S.SUBMITTED, S.RETURNED])
def test_set_academics_refused_after_submit(world: World, status: str) -> None:
    application = draft(world, status=status)
    with pytest.raises(ValidationError) as caught:
        academics(world, application, TYPED)
    assert caught.value.messages == [ACADEMICS_FROZEN]
    assert ACADEMICS_FROZEN == "The school and grades are frozen once the application is submitted."
    application.refresh_from_db()
    assert application.course == ""
    assert actions() == []


def test_set_academics_audit_names_fields_not_values(world: World) -> None:
    application = draft(world)
    academics(world, application, TYPED)
    event = AuditEvent.objects.get()
    assert event.target_id == str(application.pk)
    assert event.program == world.program
    assert event.data == {
        "fields": [
            "course",
            "gwa",
            "gwa_scale",
            "school_name",
            "school_type",
            "units",
            "year_level",
        ]
    }
    text = str(event.data)
    for value in ("Taguig Tech", "BS Biology", "88.5"):
        assert value not in text


def test_set_academics_no_change_no_audit(world: World) -> None:
    application = draft(world)
    academics(world, application, TYPED)
    academics(world, application, TYPED)
    assert actions() == ["application.academics_set"]


def staff_file(user: User, **extra: Any) -> StoredFile:
    values: dict[str, Any] = {
        "uploaded_by": user,
        "status": StoredFile.Status.READY,
        "purpose": StoredFile.Purpose.DOCUMENT,
        "sniffed_type": PDF,
        "sha256": "b" * 64,
    }
    values.update(extra)
    return StoredFileFactory.create(**values)


def requirement(world: World) -> RequiredDocument:
    return RequiredDocumentFactory.create(program=world.program, code="grades", label="Grades")


def attach(world: World, application: Application, req: RequiredDocument, file: StoredFile) -> Any:
    return attach_on_behalf(
        actor=world.actor,
        program=world.program,
        pk=application.pk,
        requirement=req,
        file_id=file.pk,
    )


def test_staff_attach_to_on_behalf_draft(world: World) -> None:
    application = draft(world)
    req = requirement(world)
    file = staff_file(world.actor)
    document = attach(world, application, req, file)
    assert document.files.get(is_current=True).version == 1
    event = AuditEvent.objects.get(action="document.uploaded")
    assert event.data == {"requirement": "grades", "version": 1}
    assert event.actor == world.actor


def test_staff_attach_replaces_declined_on_returned(world: World) -> None:
    application = draft(world, status=S.RETURNED)
    req = requirement(world)
    document = DocumentFactory.create(
        application=application,
        requirement=req,
        status=Document.Status.DECLINED,
        decline_reason="Blurry",
    )
    DocumentFileFactory.create(document=document)
    attach(world, application, req, staff_file(world.actor))
    document.refresh_from_db()
    assert document.status == Document.Status.PENDING
    assert document.decline_reason == ""
    assert document.files.get(is_current=True).version == 2


def test_staff_attach_refused_after_submit(world: World) -> None:
    application = draft(world, status=S.SUBMITTED)
    with pytest.raises(ValidationError) as caught:
        attach(world, application, requirement(world), staff_file(world.actor))
    assert caught.value.messages == ["You can't change documents after submitting."]
    assert actions() == []


def test_staff_attach_refuses_colleagues_file(world: World) -> None:
    application = draft(world)
    colleague = MembershipFactory.create(program=world.program).user
    with pytest.raises(ValidationError) as caught:
        attach(world, application, requirement(world), staff_file(colleague))
    assert caught.value.messages == ["Upload the file again."]
    assert actions() == []


def test_staff_attach_wrong_type_and_size(world: World) -> None:
    application = draft(world)
    req = requirement(world)
    RequiredDocument.objects.filter(pk=req.pk).update(accepted_types=[PDF], max_bytes=1 * MB)
    req.refresh_from_db()
    with pytest.raises(ValidationError) as caught:
        attach(world, application, req, staff_file(world.actor, sniffed_type=PNG))
    assert caught.value.messages == ["This document must be a PDF file."]
    with pytest.raises(ValidationError) as caught:
        attach(world, application, req, staff_file(world.actor, size=1 * MB + 1, sha256="c" * 64))
    assert caught.value.messages == ["This file is larger than 1 MB."]
    assert actions() == []
