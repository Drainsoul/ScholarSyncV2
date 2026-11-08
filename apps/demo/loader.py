"""Demo data loader: four verified test accounts plus sample profiles, all idempotent."""

from datetime import date
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, record_consent
from apps.demo.accounts import ACCOUNTS, PASSWORD, DemoAccount
from apps.programs.models import Program, School
from apps.programs.services import add_membership
from apps.students import services as students
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite, StudentProfile


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
        _create_unclaimed_profile(
            staff_email="staff@scholarsync.test",
            program_slug="tcu-ceaa",
            email="paolo@scholarsync.test",
        )
    return created
