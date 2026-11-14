"""Demo data loader: four verified test accounts plus sample profiles, all idempotent."""

import hashlib
import logging
import uuid
from datetime import date
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, record_consent
from apps.applications import review
from apps.applications.models import Application
from apps.applications.services import attach_document, start_application, submit_application
from apps.demo.accounts import ACCOUNTS, PASSWORD, DemoAccount
from apps.demo.samples import (
    DECLINE_REASON,
    PDF_TYPE,
    PNG_TYPE,
    RETURN_REASON,
    SAMPLE_APPLICANTS,
    SAMPLE_PDF,
    SAMPLE_PNG,
    SampleApplicant,
)
from apps.files import storage
from apps.files.models import StoredFile
from apps.programs.models import BenefitTier, Program, School
from apps.programs.selectors import application_term, required_documents_for
from apps.programs.services import add_membership
from apps.students import services as students
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite, StudentProfile

logger = logging.getLogger(__name__)


def _create(account: DemoAccount) -> None:
    if account.role == User.Role.STUDENT:
        user = User.objects.create_user(
            email=account.email, password=PASSWORD, full_name=account.full_name, role=account.role
        )
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        record_consent(user=user, request=None)
        return
    user = create_staff_user(
        actor=None,
        email=account.email,
        full_name=account.full_name,
        role=account.role,
        password=PASSWORD,
    )
    if account.program and account.level:
        add_membership(
            actor=None,
            user=user,
            program=Program.objects.get(slug=account.program),
            level=account.level,
        )


def _give_student_a_profile(email: str) -> None:
    """Carolyn's profile: 92% complete (everything but the photo). Skipped if she has one."""
    user = User.objects.get(email__iexact=email)
    if StudentProfile.objects.filter(user=user).exists():
        return
    students.update_personal(
        user=user,
        data={
            "first_name": "Carolyn",
            "last_name": "Hawkins",
            "birth_date": date(2006, 3, 14),
            "sex": StudentProfile.Sex.FEMALE,
            "phone": "+639171234567",
            "address_line": "12 Mabini Street",
            "barangay": "ususan",
            "residing_since": 2012,
            "is_registered_voter": True,
            "monthly_household_income": Decimal("18000.00"),
        },
    )
    students.add_family_member(
        user=user,
        data={
            "relation": FamilyMember.Relation.MOTHER,
            "name": "Teresa Hawkins",
            "occupation": "Vendor",
            "monthly_income": Decimal("9000.00"),
        },
    )
    students.add_education(
        user=user,
        data={
            "level": EducationRecord.Level.SHS,
            "school_name": "Ususan National High School",
            "school_type": School.Type.PUBLIC,
            "gwa_scale": School.Scale.PERCENT,
            "year_from": 2021,
            "year_to": 2023,
        },
    )
    students.add_education(
        user=user,
        data={
            "level": EducationRecord.Level.COLLEGE,
            "school": School.objects.get(name="Taguig City University"),
            "course": "BS Information Technology",
            "year_level": 2,
            "gwa": Decimal("88.50"),
            "units": 21,
            "is_current": True,
        },
    )


def _give_student_a_draft(email: str, program_slug: str) -> None:
    """Carolyn's draft application (idempotent: reuses the open one)."""
    if application_term(timezone.localdate()) is None:
        return  # No term applies today: load without a draft.
    try:
        start_application(
            user=User.objects.get(email__iexact=email),
            program=Program.objects.get(slug=program_slug),
        )
    except (ValidationError, Http404) as error:
        # Never crash the loader. Log only the error class: the service's sentence can hold
        # profile values (GWA, units, residency years), and logs never hold those.
        logger.warning("Demo draft application skipped (%s).", type(error).__name__)


def _sample_profile(user: User, applicant: SampleApplicant) -> None:
    """A TCU profile that passes every CEAA rule, as Carolyn's does."""
    students.update_personal(
        user=user,
        data={
            "first_name": applicant.first_name,
            "last_name": applicant.last_name,
            "birth_date": applicant.birth_date,
            "sex": StudentProfile.Sex.FEMALE,
            "phone": "+639171234567",
            "address_line": "12 Mabini Street",
            "barangay": "ususan",
            "residing_since": 2012,
            "is_registered_voter": True,
            "monthly_household_income": Decimal("18000.00"),
        },
    )
    students.add_family_member(
        user=user,
        data={
            "relation": FamilyMember.Relation.MOTHER,
            "name": f"Parent of {applicant.last_name}",
            "occupation": "Vendor",
            "monthly_income": Decimal("9000.00"),
        },
    )
    students.add_education(
        user=user,
        data={
            "level": EducationRecord.Level.SHS,
            "school_name": "Ususan National High School",
            "school_type": School.Type.PUBLIC,
            "gwa_scale": School.Scale.PERCENT,
            "year_from": 2021,
            "year_to": 2023,
        },
    )
    students.add_education(
        user=user,
        data={
            "level": EducationRecord.Level.COLLEGE,
            "school": School.objects.get(name="Taguig City University"),
            "course": "BS Information Technology",
            "year_level": 2,
            "gwa": Decimal("88.50"),
            "units": 21,
            "is_current": True,
        },
    )


def _sample_file(user: User, accepted_types: list[str], number: int) -> StoredFile:
    """Put a sample file to storage and record it as ready, as a confirmed upload would."""
    pdf = PDF_TYPE in accepted_types
    body, content_type = (SAMPLE_PDF, PDF_TYPE) if pdf else (SAMPLE_PNG, PNG_TYPE)
    file_id = uuid.uuid4()
    key = f"files/{StoredFile.Purpose.DOCUMENT}/{file_id}"
    storage.put(key=key, body=body, content_type=content_type)
    return StoredFile.objects.create(
        id=file_id,
        key=key,
        status=StoredFile.Status.READY,
        purpose=StoredFile.Purpose.DOCUMENT,
        original_name=f"sample-{number}.{'pdf' if pdf else 'png'}",
        declared_type=content_type,
        sniffed_type=content_type,
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        uploaded_by=user,
    )


def _submit_sample(applicant: SampleApplicant, program: Program) -> Application:
    user = User.objects.create_user(
        email=applicant.email,
        password=None,
        full_name=f"{applicant.first_name} {applicant.last_name}",
        role=User.Role.STUDENT,
    )
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    record_consent(user=user, request=None)
    _sample_profile(user, applicant)
    application = start_application(user=user, program=program)
    for number, requirement in enumerate(required_documents_for(program, "new"), start=1):
        file = _sample_file(user, requirement.accepted_types, number)
        attach_document(
            user=user, application=application, requirement=requirement, file_id=file.id
        )
    return submit_application(user=user, application=application, tier=None)


def _first_document_id(application: Application) -> int:
    document = application.documents.order_by("requirement__sort_order", "pk").first()
    assert document is not None
    return document.pk


def _decide_samples(applications: dict[str, Application]) -> None:
    """Set the states staff would: one under review, one returned, one approved."""
    staff = User.objects.get(email__iexact="staff@scholarsync.test")
    program = Program.objects.get(slug="tcu-ceaa")
    under_review = applications["under_review"]
    review.start_review(actor=staff, program=program, application=under_review)
    review.approve_document(
        actor=staff,
        program=program,
        application=under_review,
        document_id=_first_document_id(under_review),
    )
    returned = applications["returned"]
    review.start_review(actor=staff, program=program, application=returned)
    review.decline_document(
        actor=staff,
        program=program,
        application=returned,
        document_id=_first_document_id(returned),
        reason=DECLINE_REASON,
    )
    review.return_application(
        actor=staff, program=program, application=returned, reason=RETURN_REASON
    )
    approved = applications["approved"]
    review.start_review(actor=staff, program=program, application=approved)
    for document in approved.documents.all():
        review.approve_document(
            actor=staff, program=program, application=approved, document_id=document.pk
        )
    review.approve_application(
        actor=staff,
        program=program,
        application=approved,
        tier=BenefitTier.objects.get(program=program, code="standard"),
    )


def _give_staff_a_queue() -> None:
    """Five sample TCU CEAA applicants for staff to review (idempotent; needs storage)."""
    if User.objects.filter(email__iexact=SAMPLE_APPLICANTS[0].email).exists():
        return
    if not storage.is_configured():
        logger.warning("Demo review samples skipped (%s).", "StorageNotConfigured")
        return
    if application_term(timezone.localdate()) is None:
        return  # No term applies today: load without samples.
    program = Program.objects.get(slug="tcu-ceaa")
    try:
        with transaction.atomic():  # all five or none: a failure leaves no half-built queue
            applications = {a.state: _submit_sample(a, program) for a in SAMPLE_APPLICANTS}
            _decide_samples(applications)
    except (
        storage.StorageUnavailable,
        ValidationError,
        Http404,
        PermissionDenied,
        ObjectDoesNotExist,
    ) as error:
        # Explore mode boots through load_demo: a refused sample must never stop it.
        # Log only the error class: service sentences can hold profile values.
        logger.warning("Demo review samples skipped (%s).", type(error).__name__)


def _create_unclaimed_profile(*, staff_email: str, program_slug: str, email: str) -> None:
    """Paolo's staff-created profile and invite (mail goes to Mailpit). Skipped if invited."""
    if ProfileInvite.objects.filter(email=email).exists():
        return
    students.create_staff_profile(
        actor=User.objects.get(email__iexact=staff_email),
        program=Program.objects.get(slug=program_slug),
        first_name="Paolo",
        middle_name="",
        last_name="Villanueva",
        suffix="",
        birth_date=date(2007, 5, 1),
        email=email,
    )


def load() -> int:
    """Create the demo accounts that are missing and return how many were created."""
    with transaction.atomic():
        call_command("seed_programs")
        created = 0
        for account in ACCOUNTS:
            if User.objects.filter(email__iexact=account.email).exists():
                continue
            _create(account)
            created += 1
        _give_student_a_profile("student@scholarsync.test")
        _give_student_a_draft("student@scholarsync.test", "lani")
        _give_staff_a_queue()
        _create_unclaimed_profile(
            staff_email="staff@scholarsync.test",
            program_slug="tcu-ceaa",
            email="paolo@scholarsync.test",
        )
    return created
