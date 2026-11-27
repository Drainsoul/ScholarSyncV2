"""The public demo's nightly reset (branch `demo`, hosted demo design section 5.4).

Every visitor shares the test accounts, so each night the copy goes back to the clean demo: the
tables are emptied, the loader adds the accounts and samples again, and only then are the files
that existed before the reset deleted. A failed load leaves the old data and its files in place.
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
    # Yesterday's keys, listed first and deleted only after the new data commits: a failed load
    # keeps the old rows and the files they point at. The loader's new files get new keys.
    old_keys = storage.list_keys()
    with transaction.atomic(), bypass():
        call_command("flush", interactive=False, verbosity=0)
        accounts_created = loader.load()
    files_deleted = storage.delete_keys(old_keys)
    cache.clear()
    result = ResetResult(files_deleted, accounts_created, round(time.monotonic() - started, 1))
    logger.info(
        "Demo reset: %s files deleted, %s accounts created in %.1f s.",
        result.files_deleted,
        result.accounts_created,
        result.seconds,
    )
    return result
