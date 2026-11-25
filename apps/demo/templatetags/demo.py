from dataclasses import dataclass

from django import template

from apps.accounts.models import User
from apps.demo.accounts import GROUPS, LISTED, LISTED_EMAILS, PASSWORD, DemoAccount

register = template.Library()


@dataclass(frozen=True)
class AccountGroup:
    name: str
    accounts: list[DemoAccount]


@register.simple_tag
def demo_account_groups() -> list[AccountGroup]:
    """The listed accounts that exist and can sign in, by group (spec §11 rev 36). One query.

    A sample the loader skipped (no storage, summer, no term) has no account, so it gets no button.
    """
    ready = {
        email.lower()
        for email in User.objects.filter(email__in=LISTED_EMAILS, is_active=True)
        .exclude(password__startswith="!")  # noqa: S106 (Django's mark of an unusable password)
        .values_list("email", flat=True)
    }
    groups = [
        AccountGroup(name, [a for a in LISTED if a.group == name and a.email in ready])
        for name in GROUPS
    ]
    return [group for group in groups if group.accounts]


@register.simple_tag
def demo_password() -> str:
    return PASSWORD
