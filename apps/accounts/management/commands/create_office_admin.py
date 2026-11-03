import os
from getpass import getpass
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.managers import normalise_email
from apps.accounts.models import User
from apps.accounts.services import create_staff_user

PASSWORD_VARIABLE = "OFFICE_ADMIN_PASSWORD"  # noqa: S105


class Command(BaseCommand):
    help = "Create the first scholarship-office account. Never prints the email address."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--full-name", required=True)
        parser.add_argument(
            "--no-input",
            action="store_true",
            help=f"Read the password from the {PASSWORD_VARIABLE} environment variable.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = normalise_email(options["email"])
        if User.objects.filter(email=email).exists():
            raise CommandError("An account with the address given to --email already exists.")
        password = self._password(no_input=options["no_input"])
        try:
            create_staff_user(
                actor=None,
                email=email,
                full_name=options["full_name"].strip(),
                role=User.Role.SUPER_ADMIN,
                password=password,
            )
        except ValidationError as error:
            # Password-validator messages never include the address.
            raise CommandError("; ".join(error.messages)) from None
        self.stdout.write("Office account created. Log in at /accounts/login/.")

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
