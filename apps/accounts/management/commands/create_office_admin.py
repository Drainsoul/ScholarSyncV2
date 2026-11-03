import os
from getpass import getpass
from typing import Any

from allauth.account.models import EmailAddress
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.managers import normalise_email
from apps.accounts.models import User
from apps.accounts.services import create_staff_user, promote_to_office

PASSWORD_VARIABLE = "OFFICE_ADMIN_PASSWORD"  # noqa: S105


class Command(BaseCommand):
    help = (
        "Create the first scholarship-office account, or take over an account that signed up with "
        "the same address. Never prints the email address."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--full-name", required=True)
        parser.add_argument(
            "--no-input",
            action="store_true",
            help=f"Read the password from the {PASSWORD_VARIABLE} environment variable.",
        )
        parser.add_argument(
            "--promote-existing",
            action="store_true",
            help="Make an existing account with a verified address the office account.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = normalise_email(options["email"])
        full_name = options["full_name"].strip()
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            verified = EmailAddress.objects.filter(
                user=existing, email__iexact=email, verified=True
            ).exists()
            # A never-verified signup was typed by someone who may not own the address, so the
            # operator takes it over. A verified one is somebody's real account: ask first.
            if verified and not options["promote_existing"]:
                raise CommandError(
                    "An account with the address given to --email already exists and its address "
                    "is verified. To make it the office account, run again with "
                    "--promote-existing."
                )
        password = self._password(no_input=options["no_input"])
        try:
            if existing is None:
                create_staff_user(
                    actor=None,
                    email=email,
                    full_name=full_name,
                    role=User.Role.SUPER_ADMIN,
                    password=password,
                )
            else:
                promote_to_office(user=existing, full_name=full_name, password=password)
        except ValidationError as error:
            # Password-validator messages never include the address.
            raise CommandError("; ".join(error.messages)) from None
        if existing is None:
            self.stdout.write("Office account created. Log in at /accounts/login/.")
        else:
            self.stdout.write(
                "The existing account is now the office account. Log in at /accounts/login/."
            )

    def _password(self, *, no_input: bool) -> str:
        if no_input:
            password = os.environ.get(PASSWORD_VARIABLE, "")
            if not password:
                raise CommandError(f"With --no-input, set the {PASSWORD_VARIABLE} variable.")
            return password
        first = getpass("Password: ")
        if first != getpass("Password (again): "):
            raise CommandError("The two passwords do not match.")
        return first
