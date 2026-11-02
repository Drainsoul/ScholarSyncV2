import argparse
import logging
import signal
import threading
from types import FrameType
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    """argparse type: a whole number of seconds above zero (0 would spin the loop)."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {number}")
    return number


class Command(BaseCommand):
    help = "Run the housekeeping cycle every interval (the worker container)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--interval", type=positive_int, default=300, help="Seconds between cycles."
        )
        parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")

    def _cycle(self) -> None:
        close_old_connections()
        try:
            call_command("cleanup")
        except Exception:
            logger.exception("Worker cycle failed; will retry next interval.")
        finally:
            close_old_connections()

    def handle(self, *args: Any, **options: Any) -> None:
        stop = threading.Event()

        def request_stop(signum: int, frame: FrameType | None) -> None:
            stop.set()

        previous = {
            sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            while not stop.is_set():
                self._cycle()
                if options["once"]:
                    return
                stop.wait(options["interval"])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        self.stdout.write("Worker stopped.")
