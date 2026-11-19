"""Encryption for 2FA secrets at rest (ASVS 5.0 V6.5.2).

allauth stores the TOTP secret and the recovery-code seed through `MFAAdapter.encrypt/decrypt`.
They are Fernet tokens under keys derived from `SECRET_KEY` and every key in
`SECRET_KEY_FALLBACKS`: the current key encrypts, and any of them decrypts, so a rotated key keeps
working while the old one stays in the fallbacks. allauth never rewrites a stored secret, so after
a rotation `manage.py reencrypt_mfa_secrets` moves them all to the current key. The data migration
shares this module.
"""

import base64
from collections.abc import Callable
from typing import Any

from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

PREFIX = "fernet:"
_INFO = b"scholarsync mfa secrets v1"


def _fernet_key(secret_key: str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO)
    return base64.urlsafe_b64encode(hkdf.derive(secret_key.encode()))


def _fernet() -> MultiFernet:
    keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return MultiFernet([Fernet(_fernet_key(key)) for key in keys])


def is_encrypted(value: str) -> bool:
    return value.startswith(PREFIX)


def encrypt(text: str) -> str:
    return PREFIX + _fernet().encrypt(text.encode()).decode("ascii")


def decrypt(value: str) -> str:
    """A value without the prefix was stored before encryption and comes back unchanged. One
    whose key is gone raises `InvalidToken`: never a guessable stand-in secret."""
    if not is_encrypted(value):
        return value
    return _fernet().decrypt(value.removeprefix(PREFIX).encode("ascii")).decode()


def rotate(value: str) -> str:
    """The value encrypted under the current key, whichever key (or none) it had before."""
    if not is_encrypted(value):
        return encrypt(value)
    return PREFIX + _fernet().rotate(value.removeprefix(PREFIX).encode("ascii")).decode("ascii")


def encrypt_new(value: str) -> str | None:
    """For `convert_rows`: encrypt a value stored in the clear, leave an encrypted one alone."""
    return None if is_encrypted(value) else encrypt(value)


def decrypt_old(value: str) -> str | None:
    """For `convert_rows`: decrypt an encrypted value, leave a clear one alone."""
    return decrypt(value) if is_encrypted(value) else None


def convert_rows(authenticator_model: Any, change: Callable[[str], str | None]) -> int:
    """Apply `change` to every stored secret: the TOTP secret, the recovery-code seed and any
    recovery codes migrated from older 2FA packages. `change` returns the new value, or None to
    keep the old one. Takes the model so a migration can pass its historical one; returns the
    number of rows changed."""
    changed_rows = 0
    rows = authenticator_model.objects.filter(type__in=["totp", "recovery_codes"]).order_by("pk")
    for row in rows.iterator():
        data = dict(row.data)
        changed = False
        for key in ("secret", "seed"):
            value = data.get(key)
            if isinstance(value, str) and (new := change(value)) is not None:
                data[key] = new
                changed = True
        codes = data.get("migrated_codes")
        if isinstance(codes, list):
            new_codes = [change(code) if isinstance(code, str) else None for code in codes]
            if any(code is not None for code in new_codes):
                data["migrated_codes"] = [
                    old if new is None else new for old, new in zip(codes, new_codes, strict=True)
                ]
                changed = True
        if changed:
            row.data = data
            row.save(update_fields=["data"])
            changed_rows += 1
    return changed_rows
