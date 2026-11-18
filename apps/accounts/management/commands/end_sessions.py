"""End every session of one account (spec §10, M13; ASVS V7.4.5): the operator's tool for a
student account; the office uses "Sign out everywhere" on staff accounts."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services import end_all_sessions


class Command(BaseCommand):
    help = "Sign one account out everywhere, by email."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("No account has that email.")
        ended = end_all_sessions(actor=None, user=user)
        # Never print the address: logs keep only ids.
        self.stdout.write(f"Ended {ended} session(s) of account {user.pk}.")
