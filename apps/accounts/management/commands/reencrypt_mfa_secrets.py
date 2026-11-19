"""Encrypt every stored 2FA secret under the current DJANGO_SECRET_KEY (ASVS 5.0 V6.5.2). Run it
after a key rotation, while the old key is still in DJANGO_SECRET_KEY_FALLBACKS."""

from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.services import reencrypt_mfa_secrets


class Command(BaseCommand):
    help = "Re-encrypt 2FA secrets under the current secret key, after a key rotation."

    def handle(self, *args: Any, **options: Any) -> None:
        changed = reencrypt_mfa_secrets(actor=None)
        self.stdout.write(f"Re-encrypted the secrets of {changed} authenticator(s).")
