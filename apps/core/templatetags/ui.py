"""Design-system template tags (spec §12). Load with {% load ui %}."""

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString

register = template.Library()

CENTAVO = Decimal("0.01")


@register.simple_tag
def icon(name: str, label: str = "") -> SafeString:
    """An icon from the sprite. Decorative unless it has a label (then it is the only content)."""
    href = f"{static('dist/icons.svg')}#{name}"
    if label:
        return format_html(
            '<svg class="icon" role="img" aria-label="{}" focusable="false">'
            '<use href="{}"></use></svg>',
            label,
            href,
        )
    return format_html(
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="{}"></use></svg>', href
    )


@register.filter
def peso(value: Decimal | int | None) -> str:
    """₱1,234.50. Money is Decimal (CLAUDE.md); a float here is a bug, so it raises."""
    if value is None:
        return "—"
    if isinstance(value, float):
        raise TypeError("peso() takes Decimal or int, not float")
    amount = Decimal(value).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return f"{sign}₱{abs(amount):,.2f}"
