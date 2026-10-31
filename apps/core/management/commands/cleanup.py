from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete expired housekeeping rows (sessions for now)."

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("clearsessions")
