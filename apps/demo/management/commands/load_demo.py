from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.demo import loader
from apps.demo.lockdown import bypass


class Command(BaseCommand):
    help = "Load the demo accounts and sample data (local only)."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEMO_ACTIVE:
            raise CommandError(
                "The demo is off in production mode. It only runs locally (docs/SETUP.md)."
            )
        with bypass():  # the public demo's guards would refuse the password sync
            count = loader.load()
        self.stdout.write(f"Demo data: {count} new objects.")
