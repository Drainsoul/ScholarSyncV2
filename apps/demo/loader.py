"""Demo data loader: four verified test accounts plus sample profiles, all idempotent."""

import hashlib
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from allauth.account.models import EmailAddress
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, record_consent
from apps.applications import behalf, review
from apps.applications.models import Application
from apps.applications.services import attach_document, start_application, submit_application
from apps.awards.models import Award, ScholarTerm
from apps.awards.services import AwardData, TermData, change_status, create_award
from apps.demo.accounts import ACCOUNTS, PASSWORD, DemoAccount
from apps.demo.office import give_office_samples
from apps.demo.reports import give_report_samples
from apps.demo.samples import (
    DECLINE_REASON,
    DEMO_BUDGET,
    DEMO_CLAIM_LOCATION,
    DEMO_SCHEDULE_NOTE,
    HOLD_REASON,
    MANUAL_SCHOLAR,
    OVERRIDE_REASON,
    PDF_TYPE,
    PNG_TYPE,
    RETURN_REASON,
    SAMPLE_APPLICANTS,
    SAMPLE_PDF,
    SAMPLE_PNG,
    SAMPLE_SCHOLARS,
    WALK_IN_DRAFT,
    WALK_IN_SUBMITTED,
    SampleApplicant,
    SampleScholar,
    WalkIn,
)
from apps.demo.workspace import give_workspace_samples
from apps.files import storage
from apps.files.models import StoredFile
from apps.money import services as money
from apps.money.models import Disbursement, DistributionSchedule
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.selectors import application_term, current_term, required_documents_for
from apps.programs.services import add_membership
from apps.programs.terms import school_year_terms
from apps.students import services as students
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite, StudentProfile

logger = logging.getLogger(__name__)

# Five valid TCU CEAA rows (Faker en_PH names) for trying Scholars > Import.
SAMPLE_IMPORT = Path(__file__).resolve().parent / "data" / "scholars-import.csv"


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


def _walk_in_application(
    program: Program, staff: User, walk_in: WalkIn, gwa: Decimal
) -> Application:
    """A staff-created profile (invite goes to Mailpit) with an on-behalf draft and academics."""
    profile, _ = students.create_staff_profile(
        actor=staff,
        program=program,
        first_name=walk_in.first_name,
        middle_name="",
        last_name=walk_in.last_name,
        suffix="",
        birth_date=walk_in.birth_date,
        email=walk_in.email,
    )
    application = behalf.start_on_behalf(actor=staff, program=program, profile_id=profile.pk)
    return behalf.set_academics(
        actor=staff,
        program=program,
        pk=application.pk,
        data={
            "school": School.objects.get(name="Taguig City University"),
            "course": "BS Information Technology",
            "year_level": 2,
            "gwa": gwa,
            "units": 21,
        },
    )


def _file_submitted_walk_in(program: Program, staff: User) -> None:
    application = _walk_in_application(program, staff, WALK_IN_SUBMITTED, Decimal("78.00"))
    for number, requirement in enumerate(required_documents_for(program, "new"), start=1):
        file = _sample_file(staff, requirement.accepted_types, number)
        behalf.attach_on_behalf(
            actor=staff,
            program=program,
            pk=application.pk,
            requirement=requirement,
            file_id=file.id,
        )
    behalf.submit_on_behalf(
        actor=staff,
        program=program,
        pk=application.pk,
        tier=None,
        override_reason=OVERRIDE_REASON,
    )


def _give_staff_on_behalf_samples() -> None:
    """Two walk-ins: one submitted with overridden rules (needs storage), one staff draft."""
    if application_term(timezone.localdate()) is None:
        return  # No term applies today: load without on-behalf samples.
    program = Program.objects.get(slug="tcu-ceaa")
    staff = User.objects.get(email__iexact="staff@scholarsync.test")
    if storage.is_configured():
        if not ProfileInvite.objects.filter(email=WALK_IN_SUBMITTED.email).exists():
            try:
                with transaction.atomic():  # a failure leaves no half-filed application
                    _file_submitted_walk_in(program, staff)
            except (
                storage.StorageUnavailable,
                ValidationError,
                Http404,
                PermissionDenied,
                ObjectDoesNotExist,
            ) as error:
                logger.warning(
                    "Demo on-behalf submitted sample skipped (%s).", type(error).__name__
                )
    else:
        logger.warning("Demo on-behalf submitted sample skipped (%s).", "StorageNotConfigured")
    if not ProfileInvite.objects.filter(email=WALK_IN_DRAFT.email).exists():
        try:
            with transaction.atomic():
                _walk_in_application(program, staff, WALK_IN_DRAFT, Decimal("88.50"))
        except (ValidationError, Http404, PermissionDenied, ObjectDoesNotExist) as error:
            logger.warning("Demo on-behalf draft skipped (%s).", type(error).__name__)


def _ensure_previous_term() -> AcademicTerm | None:
    """The semester before the current one, created when missing (the seed creates only the
    current school year). None in summer or with no term: then there are no scholar samples."""
    current = application_term(timezone.localdate())
    if current is None or current.term == AcademicTerm.Term.SUMMER:
        return None
    if current.term == AcademicTerm.Term.FIRST:
        year, number = current.school_year_start - 1, AcademicTerm.Term.SECOND
    else:
        year, number = current.school_year_start, AcademicTerm.Term.FIRST
    spec = school_year_terms(date(year, 8, 1))[number - 1]
    term, _ = AcademicTerm.objects.get_or_create(
        school_year_start=year,
        term=number,
        defaults={"starts_on": spec.starts_on, "ends_on": spec.ends_on},
    )
    return term


def _sample_scholar(scholar: SampleScholar, program: Program, previous: AcademicTerm) -> Award:
    user = User.objects.create_user(
        email=scholar.email,
        password=PASSWORD,
        full_name=f"{scholar.first_name} {scholar.last_name}",
        role=User.Role.STUDENT,
    )
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    record_consent(user=user, request=None)
    applicant = SampleApplicant(
        scholar.email, scholar.first_name, scholar.last_name, scholar.birth_date, scholar.state
    )
    _sample_profile(user, applicant)
    profile = StudentProfile.objects.get(user=user)
    tier = (
        BenefitTier.objects.filter(program=program, code="standard")
        .order_by("-effective_from__sort_key")
        .first()
    )
    assert tier is not None
    # Written with the ORM (M9): no service creates an award in a past term until
    # the M9b import, and the samples need a scholar whose last term is behind them.
    award = Award.objects.create(
        profile=profile,
        program=program,
        tier=tier,
        status=Award.Status.ACTIVE,
        source=Award.Source.MANUAL,
        started_term=previous,
    )
    ScholarTerm.objects.create(
        award=award,
        term=previous,
        tier=tier,
        school=School.objects.get(name="Taguig City University"),
        school_type=School.Type.LCU,
        gwa_scale=School.Scale.PERCENT,
        gwa=scholar.gwa,
        units=21,
        year_level=1,
        course="BS Information Technology",
        compliance=ScholarTerm.Compliance.COMPLETE,
    )
    return award


def _give_staff_scholars() -> None:
    """Three TCU CEAA scholars from last semester (idempotent): due, at risk and on hold."""
    if User.objects.filter(email__iexact=SAMPLE_SCHOLARS[0].email).exists():
        return
    previous = _ensure_previous_term()
    if previous is None:
        return  # summer, or no term: nobody renews
    program = Program.objects.get(slug="tcu-ceaa")
    staff = User.objects.get(email__iexact="staff@scholarsync.test")
    try:
        with transaction.atomic():  # all three or none
            awards = {s.state: _sample_scholar(s, program, previous) for s in SAMPLE_SCHOLARS}
            change_status(
                actor=staff,
                program=program,
                award=awards["on_hold"],
                to=Award.Status.SUSPENDED,
                reason=HOLD_REASON,
            )
    except (ValidationError, Http404, PermissionDenied, ObjectDoesNotExist) as error:
        # Log only the error class: service sentences can hold profile values.
        logger.warning("Demo scholar samples skipped (%s).", type(error).__name__)


def _give_staff_a_manual_scholar() -> None:
    """Felipe: a TCU CEAA walk-in given an award by hand, with no account (idempotent)."""
    program = Program.objects.get(slug="tcu-ceaa")
    found = StudentProfile.objects.filter(
        created_for=program,
        first_name=MANUAL_SCHOLAR.first_name,
        last_name=MANUAL_SCHOLAR.last_name,
        birth_date=MANUAL_SCHOLAR.birth_date,
    )
    if found.exists():
        return
    term = current_term()
    if term is None:
        return
    staff = User.objects.get(email__iexact="staff@scholarsync.test")
    try:
        with transaction.atomic():
            # Written with the ORM: the profile services always send an invite, and Felipe
            # stands for the walk-ins who never give an address (an import makes the same rows).
            profile = StudentProfile.objects.create(
                first_name=MANUAL_SCHOLAR.first_name,
                last_name=MANUAL_SCHOLAR.last_name,
                birth_date=MANUAL_SCHOLAR.birth_date,
                created_by=staff,
                created_for=program,
            )
            create_award(
                actor=staff,
                program=program,
                profile_id=profile.pk,
                data=AwardData(
                    tier_code="standard",
                    student_number="2026-0042",
                    notes="Walk-in at the scholarship office.",
                    record=TermData(
                        term=term,
                        school=School.objects.get(name="Taguig City University"),
                        school_name="",
                        school_type="",
                        gwa_scale="",
                        course="BS Accountancy",
                        year_level=1,
                        gwa=MANUAL_SCHOLAR.gwa,
                        units=21,
                        compliance_checked=True,
                    ),
                ),
                source=Award.Source.MANUAL,
            )
    except (ValidationError, Http404, PermissionDenied, ObjectDoesNotExist) as error:
        # Log only the error class: service sentences can hold profile values.
        logger.warning("Demo manual scholar skipped (%s).", type(error).__name__)


def _demo_schedule(head: User, program: Program, term: AcademicTerm, day: date) -> int:
    schedule = money.save_schedule(
        actor=head,
        program=program,
        schedule_id=None,
        data=money.ScheduleData(
            term=term,
            distribution_date=day,
            claim_location=program.claim_location_default or DEMO_CLAIM_LOCATION,
            frequency_label="Once a semester",
            notes=DEMO_SCHEDULE_NOTE,
        ),
    )
    money.set_published(actor=head, program=program, schedule_id=schedule.pk, published=True)
    money.generate(actor=head, program=program, schedule_id=schedule.pk)
    return schedule.pk


def _give_staff_money() -> None:
    """TCU CEAA payouts (idempotent): last semester's day is past (Carmela received, Daniel
    approved; Elena is on hold, so generation skips her), and the current term's day is two
    weeks away with Felipe prepared. Plus this year's budget."""
    program = Program.objects.get(slug="tcu-ceaa")
    if DistributionSchedule.objects.filter(program=program, notes=DEMO_SCHEDULE_NOTE).exists():
        return
    previous = _ensure_previous_term()
    term = current_term()
    if previous is None or term is None:
        return
    head = User.objects.get(email__iexact="head@scholarsync.test")
    today = timezone.localdate()
    try:
        with transaction.atomic():
            past = _demo_schedule(head, program, previous, previous.ends_on)
            names = {s.state: s.first_name for s in SAMPLE_SCHOLARS}
            rows = {
                row.scholar_term.award.profile.first_name: row.pk
                for row in Disbursement.objects.filter(schedule_id=past).select_related(
                    "scholar_term__award__profile"
                )
            }
            for state in ("due", "at_risk"):
                money.approve(
                    actor=head,
                    program=program,
                    schedule_id=past,
                    disbursement_id=rows[names[state]],
                )
            money.release(
                actor=head,
                program=program,
                schedule_id=past,
                disbursement_id=rows[names["due"]],
            )
            _demo_schedule(head, program, term, today + timedelta(days=14))
            money.set_budget(actor=head, program=program, year=today.year, amount=DEMO_BUDGET)
    except (ValidationError, Http404, PermissionDenied, ObjectDoesNotExist, KeyError) as error:
        # Log only the error class: service sentences can hold profile values.
        logger.warning("Demo money samples skipped (%s).", type(error).__name__)


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
        _give_staff_on_behalf_samples()
        _give_staff_scholars()
        _give_staff_a_manual_scholar()
        _give_staff_money()
        give_workspace_samples()
        give_office_samples()
        give_report_samples()
    return created
