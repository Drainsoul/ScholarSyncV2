import time
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the housekeeping cycle every interval (the worker container)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles.")
        parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            while True:
                call_command("cleanup")
                if options["once"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped.")
