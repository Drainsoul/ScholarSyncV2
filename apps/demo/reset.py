"""The public demo's nightly reset (branch `demo`, hosted demo design section 5.4).

Every visitor shares the test accounts, so each night the copy goes back to the clean demo: the
bucket is emptied, every table is emptied, and the loader adds the accounts and samples again.
The database part is one transaction, so a failed load leaves the old data in place.
"""

import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction

from apps.demo import loader
from apps.demo.lockdown import bypass
from apps.files import storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResetResult:
    files_deleted: int
    accounts_created: int
    seconds: float


def reset() -> ResetResult:
    if not (settings.DEMO_ACTIVE and getattr(settings, "PUBLIC_DEMO", False)):
        raise RuntimeError("Reset runs only in the public demo.")
    started = time.monotonic()
    files_deleted = storage.delete_all()
    with transaction.atomic(), bypass():
        call_command("flush", interactive=False, verbosity=0)
        accounts_created = loader.load()
    cache.clear()
    result = ResetResult(files_deleted, accounts_created, round(time.monotonic() - started, 1))
    logger.info(
        "Demo reset: %s files deleted, %s accounts created in %.1f s.",
        result.files_deleted,
        result.accounts_created,
        result.seconds,
    )
    return result
