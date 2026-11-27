from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.demo import reset


class Command(BaseCommand):
    help = "Empty the public demo's storage and database and load the demo again (branch `demo`)."

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = reset.reset()
        except RuntimeError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            f"Demo reset: {result.files_deleted} files deleted, "
            f"{result.accounts_created} accounts created in {result.seconds:.1f} s."
        )
