"""Refuse passwords known from data breaches (spec §10, M13; ASVS V6.2.12).

Have I Been Pwned's range API takes only the first 5 hex characters of the password's SHA-1 and
returns every suffix with that prefix (k-anonymity), so neither the password nor its full hash
leaves the server. The check fails open: if the service can't be reached, the password is
accepted and a warning (with no password data) is logged."""

import hashlib
import logging
import urllib.request
from typing import Any

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
TIMEOUT_SECONDS = 3
MESSAGE = "This password has appeared in a data breach. Choose another one."


def breached(password: str) -> bool:
    """True when the password's SHA-1 suffix is in the range the API returns for its prefix."""
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    request = urllib.request.Request(  # noqa: S310 - a fixed https URL
        RANGE_URL.format(prefix=prefix),
        headers={"User-Agent": "ScholarSync password check", "Add-Padding": "true"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix and count.strip() not in {"", "0"}:
            return True
    return False


class BreachedPasswordValidator:
    def validate(self, password: str, user: Any = None) -> None:
        try:
            found = breached(password)
        except Exception as error:  # noqa: BLE001 - any failure fails open
            logger.warning("Breached-password check skipped (%s).", type(error).__name__)
            return
        if found:
            raise ValidationError(MESSAGE, code="password_breached")

    def get_help_text(self) -> str:
        return "Your password can't be one that appeared in a known data breach."
