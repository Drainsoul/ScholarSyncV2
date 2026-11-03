"""Demo data loader: four verified test accounts, created idempotently by email."""

from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services import create_staff_user, record_consent
from apps.demo.accounts import ACCOUNTS, PASSWORD, DemoAccount
from apps.programs.models import Program
from apps.programs.services import add_membership


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
    return created
