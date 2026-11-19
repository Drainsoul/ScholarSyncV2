"""2FA secrets are encrypted at rest (ASVS 5.0 V6.5.2)."""

import importlib
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
    yield_hotp_counters_from_time,
)
from cryptography.fernet import InvalidToken
from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import connection

from apps.accounts import mfa_secrets
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from config.tests.test_settings import settings_values

pytestmark = pytest.mark.django_db

migration = importlib.import_module("apps.accounts.migrations.0003_encrypt_mfa_secrets")


def _code(secret: str) -> str:
    counter = next(yield_hotp_counters_from_time())
    return str(format_hotp_value(hotp_value(secret, counter)))


def _raw_rows() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT data::text FROM mfa_authenticator")
        return "\n".join(row[0] for row in cursor.fetchall())


def test_totp_secret_is_stored_encrypted_and_still_verifies() -> None:
    user = UserFactory.create(verified=True)
    secret = generate_totp_secret()
    totp = TOTP.activate(user, secret)
    stored = Authenticator.objects.get(pk=totp.instance.pk).data["secret"]
    assert stored.startswith("fernet:")
    assert secret not in _raw_rows()
    fresh = TOTP(Authenticator.objects.get(pk=totp.instance.pk))
    assert fresh.validate_code(_code(secret))


def test_recovery_code_seed_is_encrypted_and_codes_still_work() -> None:
    user = UserFactory.create(verified=True)
    codes = RecoveryCodes.activate(user)
    seed = mfa_secrets.decrypt(codes.instance.data["seed"])
    assert codes.instance.data["seed"].startswith("fernet:")
    assert seed not in _raw_rows()
    fresh = RecoveryCodes(Authenticator.objects.get(pk=codes.instance.pk))
    first = fresh.get_unused_codes()[0]
    assert fresh.validate_code(first)
    assert (
        first
        not in RecoveryCodes(Authenticator.objects.get(pk=codes.instance.pk)).get_unused_codes()
    )


def test_legacy_plaintext_values_still_decrypt() -> None:
    assert mfa_secrets.decrypt("JBSWY3DPEHPK3PXP") == "JBSWY3DPEHPK3PXP"
    user = UserFactory.create(verified=True)
    secret = generate_totp_secret()
    row = Authenticator.objects.create(
        user=user, type=Authenticator.Type.TOTP, data={"secret": secret}
    )
    assert TOTP(row).validate_code(_code(secret))


def test_tokens_differ_and_round_trip() -> None:
    first, second = mfa_secrets.encrypt("abc"), mfa_secrets.encrypt("abc")
    assert first != second  # Fernet adds a random IV and a timestamp
    assert mfa_secrets.decrypt(first) == mfa_secrets.decrypt(second) == "abc"


def test_old_key_decrypts_only_while_in_the_fallbacks(settings: Any) -> None:
    settings.SECRET_KEY = "old-key-" + "a" * 50
    settings.SECRET_KEY_FALLBACKS = []
    token = mfa_secrets.encrypt("s3cret")
    settings.SECRET_KEY = "new-key-" + "b" * 50
    with pytest.raises(InvalidToken):
        mfa_secrets.decrypt(token)
    settings.SECRET_KEY_FALLBACKS = ["old-key-" + "a" * 50]
    assert mfa_secrets.decrypt(token) == "s3cret"
    # New values use the current key, so they survive the fallback being dropped.
    fresh = mfa_secrets.encrypt("s3cret")
    settings.SECRET_KEY_FALLBACKS = []
    assert mfa_secrets.decrypt(fresh) == "s3cret"


def test_migration_encrypts_plaintext_rows_and_is_idempotent() -> None:
    user = UserFactory.create(verified=True)
    other = UserFactory.create(verified=True)
    secret = generate_totp_secret()
    seed = RecoveryCodes.generate_seed()
    totp = Authenticator.objects.create(
        user=user, type=Authenticator.Type.TOTP, data={"secret": secret}
    )
    codes = Authenticator.objects.create(
        user=user, type=Authenticator.Type.RECOVERY_CODES, data={"seed": seed, "used_mask": 0}
    )
    migrated = Authenticator.objects.create(
        user=other,
        type=Authenticator.Type.RECOVERY_CODES,
        data={"seed": seed, "used_mask": 0, "migrated_codes": ["11111111", "22222222"]},
    )

    migration.encrypt_secrets(django_apps, None)
    totp.refresh_from_db()
    codes.refresh_from_db()
    migrated.refresh_from_db()
    assert totp.data["secret"].startswith("fernet:")
    assert codes.data["seed"].startswith("fernet:")
    assert codes.data["used_mask"] == 0
    assert all(code.startswith("fernet:") for code in migrated.data["migrated_codes"])
    raw = _raw_rows()
    assert secret not in raw and seed not in raw and "11111111" not in raw
    assert TOTP(totp).validate_code(_code(secret))
    assert RecoveryCodes(migrated).get_unused_codes() == ["11111111", "22222222"]

    before = totp.data["secret"]
    migration.encrypt_secrets(django_apps, None)
    totp.refresh_from_db()
    assert totp.data["secret"] == before  # already prefixed: left alone

    migration.decrypt_secrets(django_apps, None)
    totp.refresh_from_db()
    codes.refresh_from_db()
    migrated.refresh_from_db()
    assert totp.data["secret"] == secret
    assert codes.data["seed"] == seed
    assert migrated.data["migrated_codes"] == ["11111111", "22222222"]


def test_secret_key_fallbacks_come_from_the_environment(tmp_path: Path) -> None:
    unset = ["DJANGO_SECRET_KEY_FALLBACKS"]
    assert settings_values(tmp_path, ["SECRET_KEY_FALLBACKS"], _unset=unset) == {
        "SECRET_KEY_FALLBACKS": []
    }
    assert settings_values(tmp_path, ["SECRET_KEY_FALLBACKS"], DJANGO_SECRET_KEY_FALLBACKS="") == {
        "SECRET_KEY_FALLBACKS": []
    }
    assert settings_values(
        tmp_path, ["SECRET_KEY_FALLBACKS"], DJANGO_SECRET_KEY_FALLBACKS="one,two"
    ) == {"SECRET_KEY_FALLBACKS": ["one", "two"]}


def test_reencrypt_command_moves_secrets_to_the_current_key(settings: Any) -> None:
    """allauth never rewrites a stored secret, so after a rotation the operator runs the command
    before dropping the old key from the fallbacks."""
    old = "old-key-" + "a" * 50
    settings.SECRET_KEY = old
    settings.SECRET_KEY_FALLBACKS = []
    user = UserFactory.create(verified=True)
    secret = generate_totp_secret()
    totp = TOTP.activate(user, secret)
    codes = RecoveryCodes.activate(user)
    plain = Authenticator.objects.create(
        user=UserFactory.create(verified=True),
        type=Authenticator.Type.TOTP,
        data={"secret": "JBSWY3DPEHPK3PXP"},
    )
    unused = codes.get_unused_codes()

    settings.SECRET_KEY = "new-key-" + "b" * 50
    settings.SECRET_KEY_FALLBACKS = [old]
    call_command("reencrypt_mfa_secrets", stdout=StringIO())
    settings.SECRET_KEY_FALLBACKS = []

    assert TOTP(Authenticator.objects.get(pk=totp.instance.pk)).validate_code(_code(secret))
    fresh = RecoveryCodes(Authenticator.objects.get(pk=codes.instance.pk))
    assert fresh.get_unused_codes() == unused
    plain.refresh_from_db()
    assert mfa_secrets.decrypt(plain.data["secret"]) == "JBSWY3DPEHPK3PXP"
    assert "JBSWY3DPEHPK3PXP" not in _raw_rows()
    event = AuditEvent.objects.get(action="mfa.secrets_reencrypted")
    assert event.actor is None
    assert event.data == {"authenticators": 3}
