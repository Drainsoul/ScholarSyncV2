from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications import services
from apps.applications.models import Application, Document, DocumentFile
from apps.applications.selectors import open_application
from apps.applications.services import (
    attach_document,
    start_application,
    submit_application,
    withdraw_application,
)
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.awards.tests.factories import AwardFactory
from apps.core.models import AuditEvent
from apps.files.models import StoredFile
from apps.files.policy import MB, PDF, PNG
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import AcademicTerm, BenefitTier, Program, RequiredDocument, School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.students.models import EducationRecord, StudentProfile
from apps.students.tests.factories import (
    EducationRecordFactory,
    FullProfileFactory,
    ProfileFactory,
)
from apps.workspace.emails import KINDS
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)
ALREADY = "This application has already been submitted."


@pytest.fixture(autouse=True)
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


def user_of(profile: StudentProfile) -> User:
    assert profile.user is not None
    return profile.user


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


@dataclass
class World:
    term: AcademicTerm
    school: School
    program: Program
    tier: BenefitTier
    profile: StudentProfile
    education: EducationRecord
    requirement: RequiredDocument

    @property
    def user(self) -> User:
        return user_of(self.profile)


@pytest.fixture
def term() -> AcademicTerm:
    return AcademicTermFactory.create(school_year_start=2026, is_current=True)


@pytest.fixture
def world(term: AcademicTerm) -> World:
    school = SchoolFactory.create(grading_scale=School.Scale.PERCENT, type=School.Type.PRIVATE)
    program = ProgramFactory.create(min_gwa_percent=Decimal("85.00"))
    program.allowed_schools.add(school)
    tier = BenefitTierFactory.create(program=program, effective_from=term, code="full")
    profile = FullProfileFactory.create()
    education = EducationRecordFactory.create(
        profile=profile,
        school=school,
        gwa=Decimal("90.00"),
        gwa_scale=School.Scale.PERCENT,
        units=18,
        course="BS Nursing",
        year_level=2,
    )
    requirement = RequiredDocumentFactory.create(program=program, code="grades", label="Grades")
    return World(term, school, program, tier, profile, education, requirement)


def ready_file(user: User, **extra: Any) -> StoredFile:
    values: dict[str, Any] = {
        "uploaded_by": user,
        "status": StoredFile.Status.READY,
        "purpose": StoredFile.Purpose.DOCUMENT,
        "sniffed_type": PDF,
        "sha256": "b" * 64,
        "original_name": "secret-grades.pdf",
    }
    values.update(extra)
    return StoredFileFactory.create(**values)


def draft_for(world: World, **extra: Any) -> Application:
    values: dict[str, Any] = {
        "profile": world.profile,
        "program": world.program,
        "term": world.term,
    }
    values.update(extra)
    return ApplicationFactory.create(**values)


def with_documents(application: Application) -> Application:
    for requirement in RequiredDocument.objects.filter(program=application.program):
        document = DocumentFactory.create(application=application, requirement=requirement)
        DocumentFileFactory.create(document=document)
    return application


def assert_refused(call: Callable[[], object], message: str) -> None:
    with pytest.raises(ValidationError) as caught:
        call()
    assert caught.value.messages == [message]


# --- start ---------------------------------------------------------------------------------


def test_start_creates_draft_and_audits(world: World) -> None:
    application = start_application(user=world.user, program=world.program)
    assert application.status == Application.Status.DRAFT
    assert application.kind == Application.Kind.NEW
    assert application.term == world.term
    assert application.profile == world.profile
    assert application.created_by == world.user
    event = AuditEvent.objects.get()
    assert event.action == "application.started"
    assert event.target_id == str(application.pk)
    assert event.program == world.program
    assert event.data == {}


def test_start_twice_returns_same_draft(world: World) -> None:
    first = start_application(user=world.user, program=world.program)
    second = start_application(user=world.user, program=world.program)
    assert first.pk == second.pk
    assert Application.objects.count() == 1
    assert actions() == ["application.started"]


def test_start_after_integrity_error_returns_open(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another request committed a draft after this one looked for it: the first lookup misses
    # it, the insert hits the partial unique index for real, and the fallback finds it.
    competitor = draft_for(world)
    calls: list[int] = []

    def stale_then_real(*args: Any, **kwargs: Any) -> Application | None:
        calls.append(1)
        return None if len(calls) == 1 else open_application(*args, **kwargs)

    monkeypatch.setattr(services, "open_application", stale_then_real)
    application = start_application(user=world.user, program=world.program)
    assert len(calls) == 2
    assert application.pk == competitor.pk
    assert Application.objects.count() == 1
    assert actions() == []


def test_start_refuses_ineligible_with_first_reason(world: World) -> None:
    world.education.gwa = Decimal("80.00")
    world.education.save()
    assert_refused(
        lambda: start_application(user=world.user, program=world.program),
        "Your GWA of 80.00 doesn't meet this program's minimum of 85%.",
    )
    assert Application.objects.count() == 0
    assert actions() == []


def test_start_refuses_inactive_program_404(world: World) -> None:
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    with pytest.raises(Http404):
        start_application(user=world.user, program=world.program)
    assert Application.objects.count() == 0


def test_start_without_profile(term: AcademicTerm) -> None:
    program = ProgramFactory.create()
    assert_refused(
        lambda: start_application(user=UserFactory.create(), program=program),
        "Start your profile first.",
    )
    assert StudentProfile.objects.count() == 0


def test_start_refuses_staff(world: World) -> None:
    staff = UserFactory.create(role=User.Role.STAFF)
    with pytest.raises(PermissionDenied):
        start_application(user=staff, program=world.program)


def test_start_without_term(world: World) -> None:
    AcademicTerm.objects.filter(pk=world.term.pk).update(
        is_current=False, starts_on=date(2020, 8, 1), ends_on=date(2020, 12, 1)
    )
    assert_refused(
        lambda: start_application(user=world.user, program=world.program),
        "Applications aren't open: the scholarship office hasn't set up the current school term.",
    )
    assert Application.objects.count() == 0


# --- attach --------------------------------------------------------------------------------


def test_attach_creates_version_1(world: World) -> None:
    application = draft_for(world)
    file = ready_file(world.user)
    document = attach_document(
        user=world.user, application=application, requirement=world.requirement, file_id=file.pk
    )
    assert document.status == Document.Status.PENDING
    row = DocumentFile.objects.get()
    assert (row.document, row.file, row.version, row.is_current) == (document, file, 1, True)
    event = AuditEvent.objects.get()
    assert event.action == "document.uploaded"
    assert event.data == {"requirement": "grades", "version": 1}


def test_reattach_adds_version_and_moves_current(world: World) -> None:
    application = draft_for(world)
    first = ready_file(world.user)
    second = ready_file(world.user, sha256="c" * 64)
    for file in (first, second):
        attach_document(
            user=world.user,
            application=application,
            requirement=world.requirement,
            file_id=str(file.pk),
        )
    rows = list(
        DocumentFile.objects.order_by("version").values_list("file", "version", "is_current")
    )
    assert rows == [(first.pk, 1, False), (second.pk, 2, True)]
    assert Document.objects.count() == 1
    assert actions() == ["document.uploaded", "document.uploaded"]
    assert AuditEvent.objects.order_by("pk").last().data == {"requirement": "grades", "version": 2}  # type: ignore[union-attr]


AGAIN = "Upload the file again."


def _other_users_file(world: World) -> object:
    return ready_file(UserFactory.create()).pk


def _pending_file(world: World) -> object:
    return ready_file(world.user, status=StoredFile.Status.PENDING).pk


def _rejected_file(world: World) -> object:
    return ready_file(world.user, status=StoredFile.Status.REJECTED, rejected_reason="type").pk


def _photo_file(world: World) -> object:
    return ready_file(world.user, purpose=StoredFile.Purpose.PHOTO, sniffed_type=PNG).pk


def _attached_file(world: World) -> object:
    other = ApplicationFactory.create(profile=world.profile, term=world.term)
    return DocumentFileFactory.create(document__application=other).file.pk


def _garbage(world: World) -> object:
    return "garbage"


def _png_for_pdf_only(world: World) -> object:
    RequiredDocument.objects.filter(pk=world.requirement.pk).update(accepted_types=[PDF])
    return ready_file(world.user, sniffed_type=PNG).pk


def _too_large(world: World) -> object:
    RequiredDocument.objects.filter(pk=world.requirement.pk).update(max_bytes=1 * MB)
    return ready_file(world.user, size=1 * MB + 1).pk


@pytest.mark.parametrize(
    ("make_file_id", "message"),
    [
        (_other_users_file, AGAIN),
        (_pending_file, AGAIN),
        (_rejected_file, AGAIN),
        (_photo_file, AGAIN),
        (_attached_file, AGAIN),
        (_garbage, AGAIN),
        (_png_for_pdf_only, "This document must be a PDF file."),
        (_too_large, "This file is larger than 1 MB."),
    ],
    ids=[
        "other-users-file",
        "pending",
        "rejected",
        "photo",
        "already-attached",
        "garbage",
        "wrong-type",
        "too-large",
    ],
)
def test_attach_refuses_each_bad_file(
    world: World, make_file_id: Callable[[World], object], message: str
) -> None:
    application = draft_for(world)
    file_id = make_file_id(world)
    requirement = RequiredDocument.objects.get(pk=world.requirement.pk)
    documents_before = Document.objects.count()
    files_before = DocumentFile.objects.count()
    assert_refused(
        lambda: attach_document(
            user=world.user, application=application, requirement=requirement, file_id=file_id
        ),
        message,
    )
    assert Document.objects.count() == documents_before
    assert DocumentFile.objects.count() == files_before
    assert actions() == []


def test_attach_type_sentence_lists_several_types(world: World) -> None:
    RequiredDocument.objects.filter(pk=world.requirement.pk).update(accepted_types=[PNG, PDF])
    requirement = RequiredDocument.objects.get(pk=world.requirement.pk)
    file = ready_file(world.user, sniffed_type="image/jpeg")
    assert_refused(
        lambda: attach_document(
            user=world.user,
            application=draft_for(world),
            requirement=requirement,
            file_id=file.pk,
        ),
        "This document must be a PDF or PNG file.",
    )


def test_attach_other_program_requirement_404(world: World) -> None:
    application = draft_for(world)
    elsewhere = RequiredDocumentFactory.create()
    renewal_only = RequiredDocumentFactory.create(
        program=world.program, applies_to=RequiredDocument.AppliesTo.RENEWAL
    )
    file = ready_file(world.user)
    for requirement in (elsewhere, renewal_only):
        with pytest.raises(Http404):
            attach_document(
                user=world.user,
                application=application,
                requirement=requirement,
                file_id=file.pk,
            )
    assert Document.objects.count() == 0
    assert actions() == []


def test_attach_to_other_students_application_404(world: World) -> None:
    theirs = ApplicationFactory.create(program=world.program, term=world.term)
    with pytest.raises(Http404):
        attach_document(
            user=world.user,
            application=theirs,
            requirement=world.requirement,
            file_id=ready_file(world.user).pk,
        )
    assert Document.objects.count() == 0


def test_attach_after_submit_refused(world: World) -> None:
    application = draft_for(world)
    Application.objects.filter(pk=application.pk).update(
        status=Application.Status.SUBMITTED, school=world.school
    )
    assert_refused(
        lambda: attach_document(
            user=world.user,
            application=application,  # stale: still says draft
            requirement=world.requirement,
            file_id=ready_file(world.user).pk,
        ),
        "You can't change documents after submitting.",
    )
    assert Document.objects.count() == 0


def test_attach_declined_moves_to_pending(world: World) -> None:
    application = draft_for(world, status=Application.Status.RETURNED)
    document = DocumentFactory.create(
        application=application,
        requirement=world.requirement,
        status=Document.Status.DECLINED,
        decline_reason="Blurry",
    )
    DocumentFileFactory.create(document=document)
    attach_document(
        user=world.user,
        application=application,
        requirement=world.requirement,
        file_id=ready_file(world.user).pk,
    )
    document.refresh_from_db()
    assert document.status == Document.Status.PENDING
    assert document.decline_reason == ""
    assert document.files.get(is_current=True).version == 2


def test_attach_approved_refused(world: World) -> None:
    application = draft_for(world, status=Application.Status.RETURNED)
    document = DocumentFactory.create(
        application=application, requirement=world.requirement, status=Document.Status.APPROVED
    )
    DocumentFileFactory.create(document=document)
    assert_refused(
        lambda: attach_document(
            user=world.user,
            application=application,
            requirement=world.requirement,
            file_id=ready_file(world.user).pk,
        ),
        "This document has been approved and can't be replaced.",
    )
    assert DocumentFile.objects.count() == 1


def test_audit_data_has_no_file_names(world: World) -> None:
    file = ready_file(world.user, original_name="Juan-Dela-Cruz-grades.pdf")
    attach_document(
        user=world.user,
        application=draft_for(world),
        requirement=world.requirement,
        file_id=file.pk,
    )
    data = AuditEvent.objects.get().data
    assert data == {"requirement": "grades", "version": 1}
    assert "Juan" not in str(data)
    assert str(file.pk) not in str(data)


# --- submit --------------------------------------------------------------------------------


def test_submit_happy_path_snapshots_and_emails(world: World) -> None:
    application = with_documents(draft_for(world))
    submitted = submit_application(user=world.user, application=application, tier=None)

    submitted.refresh_from_db()
    assert submitted.status == Application.Status.SUBMITTED
    assert submitted.submitted_at == datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila"))
    assert submitted.requested_tier == world.tier
    assert submitted.school == world.school
    assert submitted.school_name == ""
    assert submitted.school_type == School.Type.PRIVATE  # frozen like gwa_scale
    assert submitted.gwa == Decimal("90.00")
    assert submitted.gwa_scale == School.Scale.PERCENT
    assert submitted.units == 18
    assert submitted.course == "BS Nursing"
    assert submitted.year_level == 2

    snapshot = submitted.match_snapshot
    assert set(snapshot) == {
        "version",
        "evaluated_on",
        "eligible",
        "checks",
        "tier_candidates",
        "merit_likely",
        "hint",
    }
    assert snapshot["version"] == 1
    assert snapshot["evaluated_on"] == "2026-10-15"
    assert snapshot["eligible"] is True
    assert snapshot["tier_candidates"] == ["full"]
    assert snapshot["merit_likely"] is None
    assert {check["code"] for check in snapshot["checks"]} >= {"window", "school", "gwa"}
    assert all(set(check) == {"code", "state", "reason"} for check in snapshot["checks"])
    assert all(check["state"] == "met" for check in snapshot["checks"])
    hint = snapshot["hint"]
    assert set(hint) in ({"label", "program", "merit", "probability"}, {"reason"})

    event = AuditEvent.objects.get()
    assert event.action == "application.submitted"
    assert event.data == {"tier": "full"}

    row = EmailOutbox.objects.get()
    assert row.kind == "application_received"
    assert row.to == world.user.email
    assert set(row.context) == KINDS["application_received"]
    assert row.context["program_name"] == world.program.name
    assert row.context["full_name"] == world.profile.full_name
    assert row.context["application_url"] == (
        f"{settings.SITE_URL}/me/applications/{application.pk}/"
    )


def test_submit_snapshot_keeps_typed_school(world: World) -> None:
    world.program.allowed_schools.clear()
    world.education.school = None
    world.education.school_name = "Somewhere College"
    world.education.school_type = School.Type.PUBLIC
    world.education.gwa_scale = School.Scale.PERCENT
    world.education.save()
    application = with_documents(draft_for(world))
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.school is None
    assert application.school_name == "Somewhere College"
    assert application.school_type == School.Type.PUBLIC
    assert application.match_snapshot["hint"] != {}


def test_submit_sends_the_email(
    world: World, mailoutbox, django_capture_on_commit_callbacks
) -> None:
    application = with_documents(draft_for(world))
    with django_capture_on_commit_callbacks(execute=True):
        submit_application(user=world.user, application=application, tier=None)
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.subject == f"We received your {world.program.name} application"
    assert f"/me/applications/{application.pk}/" in message.body
    assert EmailOutbox.objects.get().status == EmailOutbox.Status.SENT


def test_single_tier_is_chosen_automatically(world: World) -> None:
    application = with_documents(draft_for(world))
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.requested_tier == world.tier


def test_tier_required_when_several(world: World) -> None:
    other = BenefitTierFactory.create(program=world.program, effective_from=world.term, code="half")
    application = with_documents(draft_for(world))
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Choose an allowance tier.",
    )
    submit_application(user=world.user, application=application, tier=other)
    application.refresh_from_db()
    assert application.requested_tier == other
    assert application.match_snapshot["tier_candidates"] == ["full", "half"]


def test_inactive_tier_refused(world: World) -> None:
    BenefitTierFactory.create(program=world.program, effective_from=world.term, code="half")
    BenefitTier.objects.filter(pk=world.tier.pk).update(is_active=False)
    application = with_documents(draft_for(world))
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=world.tier),
        "Choose one of this program's allowance tiers.",
    )
    elsewhere = BenefitTierFactory.create(effective_from=world.term)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=elsewhere),
        "Choose one of this program's allowance tiers.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert actions() == []


def test_no_tiers_refused(world: World) -> None:
    BenefitTier.objects.filter(pk=world.tier.pk).update(is_active=False)
    application = with_documents(draft_for(world))
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "This program has no allowance tiers set up yet.",
    )


def test_submit_refused_when_window_closed(world: World) -> None:
    application = with_documents(draft_for(world))
    Program.objects.filter(pk=world.program.pk).update(applications_close_on=date(2026, 10, 14))
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Applications closed on 14 October 2026.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert actions() == []
    assert EmailOutbox.objects.count() == 0


def test_submit_refused_when_term_has_ended(world: World) -> None:
    old_term = AcademicTermFactory.create(school_year_start=2025)
    application = with_documents(draft_for(world, term=old_term))
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        f"This application was for {old_term}, which has ended. Withdraw it and start a new one.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_submit_refused_when_school_changed(world: World) -> None:
    application = with_documents(draft_for(world))
    world.education.school = SchoolFactory.create(grading_scale=School.Scale.PERCENT)
    world.education.save()
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        f"This program is only for students of {world.school.name}.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert actions() == []


def test_submit_refused_when_gwa_drops(world: World) -> None:
    application = with_documents(draft_for(world))
    world.education.gwa = Decimal("80.00")
    world.education.save()
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Your GWA of 80.00 doesn't meet this program's minimum of 85%.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_submit_refused_with_missing_document(world: World) -> None:
    application = with_documents(draft_for(world))
    RequiredDocumentFactory.create(program=world.program, label="Birth certificate", sort_order=5)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Upload Birth certificate before you submit.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_submit_refused_with_incomplete_personal(world: World) -> None:
    application = with_documents(draft_for(world))
    StudentProfile.objects.filter(pk=world.profile.pk).update(phone="")
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Finish your personal details before you submit.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT


def test_double_submit_refused(world: World) -> None:
    application = with_documents(draft_for(world))
    submit_application(user=world.user, application=application, tier=None)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        ALREADY,
    )
    Application.objects.filter(pk=application.pk).update(status=Application.Status.UNDER_REVIEW)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        ALREADY,
    )
    assert actions() == ["application.submitted"]
    assert EmailOutbox.objects.count() == 1


def test_submit_withdrawn_refused(world: World) -> None:
    application = with_documents(draft_for(world, status=Application.Status.WITHDRAWN))
    with pytest.raises(ValidationError):
        submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN
    assert actions() == []


def test_first_submit_sets_first_submitted_at(world: World) -> None:
    application = with_documents(draft_for(world))
    assert application.first_submitted_at is None
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.first_submitted_at == application.submitted_at
    assert application.first_submitted_at == datetime(
        2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")
    )


def test_resubmit_keeps_first_submitted_at(world: World) -> None:
    application = with_documents(draft_for(world))
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    first = application.first_submitted_at
    Application.objects.filter(pk=application.pk).update(status=Application.Status.RETURNED)
    application.refresh_from_db()
    later = datetime(2026, 10, 20, 9, 0, tzinfo=ZoneInfo("Asia/Manila"))
    with time_machine.travel(later, tick=False):
        submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.first_submitted_at == first
    assert application.submitted_at == later


def test_submit_other_students_application_404(world: World) -> None:
    theirs = with_documents(ApplicationFactory.create(program=world.program, term=world.term))
    with pytest.raises(Http404):
        submit_application(user=world.user, application=theirs, tier=None)
    theirs.refresh_from_db()
    assert theirs.status == Application.Status.DRAFT


def test_resubmit_returned_keeps_snapshot_and_skips_window(world: World) -> None:
    snapshot = {"version": 1, "evaluated_on": "2026-09-01", "eligible": True}
    application = with_documents(
        draft_for(
            world,
            status=Application.Status.RETURNED,
            match_snapshot=snapshot,
            requested_tier=world.tier,
            gwa=Decimal("91.00"),
        )
    )
    Program.objects.filter(pk=world.program.pk).update(applications_close_on=date(2026, 9, 30))
    world.education.gwa = Decimal("80.00")
    world.education.save()
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert application.match_snapshot == snapshot
    assert application.gwa == Decimal("91.00")
    assert application.requested_tier == world.tier
    assert actions() == ["application.resubmitted"]
    assert EmailOutbox.objects.get().kind == "application_received"


def test_resubmit_refused_while_a_document_is_declined(world: World) -> None:
    application = with_documents(draft_for(world, status=Application.Status.RETURNED))
    Document.objects.filter(application=application).update(status=Document.Status.DECLINED)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        "Upload Grades before you submit.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.RETURNED


# --- withdraw ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [Application.Status.DRAFT, Application.Status.SUBMITTED, Application.Status.RETURNED],
)
def test_withdraw_from_draft_submitted_returned(world: World, status: str) -> None:
    application = draft_for(world, status=status)
    withdrawn = withdraw_application(user=world.user, application=application)
    assert withdrawn.status == Application.Status.WITHDRAWN
    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN
    event = AuditEvent.objects.get()
    assert event.action == "application.withdrawn"
    assert event.target_id == str(application.pk)


def test_withdraw_under_review_refused_with_sentence(world: World) -> None:
    application = draft_for(world, status=Application.Status.UNDER_REVIEW)
    assert_refused(
        lambda: withdraw_application(user=world.user, application=application),
        "This application is being reviewed and can't be withdrawn. "
        "Contact the scholarship office.",
    )
    application.refresh_from_db()
    assert application.status == Application.Status.UNDER_REVIEW
    assert actions() == []


def test_withdraw_other_students_application_404(world: World) -> None:
    theirs = ApplicationFactory.create(program=world.program, term=world.term)
    with pytest.raises(Http404):
        withdraw_application(user=world.user, application=theirs)
    assert actions() == []


def test_services_lock_without_trusting_profile_owner(world: World) -> None:
    application = draft_for(world)
    other = ProfileFactory.create()
    assert user_of(other) != world.user
    with pytest.raises(Http404):
        withdraw_application(user=user_of(other), application=application)


def test_submit_evaluates_and_freezes_the_same_record(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A profile edit between reads must not freeze grades that were never evaluated."""
    from apps.matching import selectors as matching_selectors
    from apps.students.selectors import current_education as real

    application = with_documents(draft_for(world))
    edited = EducationRecordFactory.build(
        profile=world.profile,
        school=world.school,
        gwa=Decimal("80.00"),
        gwa_scale=School.Scale.PERCENT,
        units=18,
        course="BS Biology",
        year_level=2,
    )
    calls: list[int] = []

    def racing(profile: StudentProfile) -> EducationRecord | None:
        calls.append(1)
        return real(profile) if len(calls) == 1 else edited

    monkeypatch.setattr(services, "current_education", racing)
    monkeypatch.setattr(matching_selectors, "current_education", racing)
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert len(calls) == 1
    assert application.gwa == Decimal("90.00")
    assert application.course == "BS Nursing"


INACTIVE = "This program isn't taking applications any more. Withdraw this application."


def test_submit_inactive_program_refused(world: World) -> None:
    application = draft_for(world)  # no documents: the inactive sentence still comes first
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=None),
        INACTIVE,
    )
    application.refresh_from_db()
    assert application.status == Application.Status.DRAFT
    assert actions() == []
    assert EmailOutbox.objects.count() == 0
    withdraw_application(user=world.user, application=application)
    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN


def test_resubmit_returned_allowed_on_inactive_program(world: World) -> None:
    application = with_documents(
        draft_for(world, status=Application.Status.RETURNED, requested_tier=world.tier)
    )
    Program.objects.filter(pk=world.program.pk).update(is_active=False)
    submit_application(user=world.user, application=application, tier=None)
    application.refresh_from_db()
    assert application.status == Application.Status.SUBMITTED
    assert actions() == ["application.resubmitted"]


def test_attach_race_on_the_same_file_says_upload_again(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another attach of the same file commits after our check: a sentence, not a 500."""
    application = draft_for(world)
    first = ready_file(world.user)
    attach_document(
        user=world.user, application=application, requirement=world.requirement, file_id=first.pk
    )
    second = ready_file(world.user, sha256="c" * 64)
    other = ApplicationFactory.create(profile=world.profile, term=world.term)
    real = Document.objects.get_or_create

    def racing(**kwargs: Any) -> tuple[Document, bool]:
        DocumentFileFactory.create(document__application=other, file=second)
        return real(**kwargs)

    monkeypatch.setattr(Document.objects, "get_or_create", racing)
    assert_refused(
        lambda: attach_document(
            user=world.user,
            application=application,
            requirement=world.requirement,
            file_id=second.pk,
        ),
        AGAIN,
    )
    current = DocumentFile.objects.get(document__application=application, is_current=True)
    assert current.file == first
    assert actions() == ["document.uploaded"]


def test_start_refused_when_holding_the_scholarship(world: World) -> None:
    approved = draft_for(world, status=Application.Status.APPROVED)
    before = Application.objects.count()
    assert_refused(
        lambda: start_application(user=world.user, program=world.program),
        "You already hold this scholarship.",
    )
    approved.delete()
    AwardFactory.create(
        profile=world.profile,
        program=world.program,
        source_application=draft_for(
            world, status=Application.Status.APPROVED, term=AcademicTermFactory.create()
        ),
    )
    before = Application.objects.count()
    assert_refused(
        lambda: start_application(user=world.user, program=world.program),
        "You already hold this scholarship.",
    )
    assert Application.objects.count() == before
    assert "application.started" not in actions()


def test_start_refused_after_a_rejection_this_term(world: World) -> None:
    draft_for(world, status=Application.Status.REJECTED)
    before = Application.objects.count()
    assert_refused(
        lambda: start_application(user=world.user, program=world.program),
        f"This application wasn't approved for {world.term}. You can apply again next term.",
    )
    assert Application.objects.count() == before
    assert "application.started" not in actions()


def test_start_allowed_after_a_rejection_in_another_term(world: World) -> None:
    draft_for(world, status=Application.Status.REJECTED, term=AcademicTermFactory.create())
    application = start_application(user=world.user, program=world.program)
    assert application.status == Application.Status.DRAFT


# --- on-behalf applications are read-only for the student -----------------------------------

LOCKED_STATUSES = [Application.Status.DRAFT, Application.Status.RETURNED]


def on_behalf_for(world: World, status: str) -> Application:
    return draft_for(world, on_behalf=True, status=status)


@pytest.mark.parametrize("status", LOCKED_STATUSES)
def test_student_cannot_attach_to_on_behalf_application(world: World, status: str) -> None:
    application = on_behalf_for(world, status)
    file = ready_file(world.user)
    before = AuditEvent.objects.count()
    assert_refused(
        lambda: attach_document(
            user=world.user,
            application=application,
            requirement=world.requirement,
            file_id=file.pk,
        ),
        services.ON_BEHALF_LOCKED,
    )
    application.refresh_from_db()
    assert application.status == status
    assert not Document.objects.filter(application=application).exists()
    assert AuditEvent.objects.count() == before


@pytest.mark.parametrize("status", LOCKED_STATUSES)
def test_student_cannot_submit_on_behalf_application(world: World, status: str) -> None:
    application = with_documents(on_behalf_for(world, status))
    before = AuditEvent.objects.count()
    documents = Document.objects.filter(application=application).count()
    assert_refused(
        lambda: submit_application(user=world.user, application=application, tier=world.tier),
        services.ON_BEHALF_LOCKED,
    )
    application.refresh_from_db()
    assert application.status == status
    assert Document.objects.filter(application=application).count() == documents
    assert AuditEvent.objects.count() == before


@pytest.mark.parametrize("status", LOCKED_STATUSES)
def test_student_cannot_withdraw_on_behalf_application(world: World, status: str) -> None:
    application = with_documents(on_behalf_for(world, status))
    before = AuditEvent.objects.count()
    documents = Document.objects.filter(application=application).count()
    assert_refused(
        lambda: withdraw_application(user=world.user, application=application),
        services.ON_BEHALF_LOCKED,
    )
    application.refresh_from_db()
    assert application.status == status
    assert Document.objects.filter(application=application).count() == documents
    assert AuditEvent.objects.count() == before
