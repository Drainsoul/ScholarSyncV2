"""Password rules beyond Django's own (ASVS V6.1.2, V6.2.11)."""

from typing import Any

from django.core.exceptions import ValidationError

# The site's own words: the product, the city and the programs. Short program codes ("TCU",
# "LANI") are only refused as the "tcu-ceaa" slug, so ordinary words that contain them pass.
SITE_WORDS = ("scholarsync", "scholarship", "taguig", "tcu-ceaa", "tcuceaa")
MESSAGE = "Choose a password without the name of this site, the city or a program."


class SiteWordsValidator:
    def validate(self, password: str, user: Any = None) -> None:
        lowered = password.lower()
        if any(word in lowered for word in SITE_WORDS):
            raise ValidationError(MESSAGE, code="password_site_word")

    def get_help_text(self) -> str:
        return "Your password can't contain the name of this site, the city or a program."
