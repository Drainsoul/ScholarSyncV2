from django import template

from apps.demo.accounts import ACCOUNTS, PASSWORD, DemoAccount

register = template.Library()


@register.simple_tag
def demo_accounts() -> list[DemoAccount]:
    return ACCOUNTS


@register.simple_tag
def demo_password() -> str:
    return PASSWORD
