from typing import Any

from django.conf import settings
from django.core.management import call_command, get_commands
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migrate, create the cache table and (locally) load the demo. Safe on every start."

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("migrate", interactive=False)
        call_command("createcachetable")
        if settings.DEMO_ACTIVE and "load_demo" in get_commands():
            call_command("load_demo")
        self.stdout.write("ScholarSync is ready.")
