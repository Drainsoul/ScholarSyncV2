"""Encrypt the 2FA secrets stored before `MFAAdapter` encrypted them (ASVS 5.0 V6.5.2)."""

from typing import Any

from django.db import migrations

from apps.accounts import mfa_secrets


def encrypt_secrets(apps: Any, schema_editor: Any) -> None:
    mfa_secrets.convert_rows(apps.get_model("mfa", "Authenticator"), mfa_secrets.encrypt_new)


def decrypt_secrets(apps: Any, schema_editor: Any) -> None:
    mfa_secrets.convert_rows(apps.get_model("mfa", "Authenticator"), mfa_secrets.decrypt_old)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_consentrecord"),
        ("mfa", "0003_authenticator_type_uniq"),
    ]

    operations = [
        migrations.RunPython(encrypt_secrets, decrypt_secrets),
    ]
