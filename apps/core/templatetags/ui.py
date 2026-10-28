"""Design-system template tags (spec §12). Load with {% load ui %}."""

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.core.paginator import Page
from django.forms import BoundField
from django.template import Context
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString

register = template.Library()

CENTAVO = Decimal("0.01")
GROUP_WIDGETS = {"radioselect", "checkboxselectmultiple"}


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


@register.inclusion_tag("components/field.html")
def field(bound_field: BoundField) -> dict[str, object]:
    """Label, help, error and widget for one form field, with the ARIA links between them."""
    help_id = f"{bound_field.auto_id}-help"
    error_id = f"{bound_field.auto_id}-error"
    described_by = [
        element_id
        for element_id, present in (
            (help_id, bound_field.help_text),
            (error_id, bound_field.errors),
        )
        if present
    ]
    attrs: dict[str, str | bool] = {}
    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    widget_type = bound_field.widget_type
    layout = (
        "check"
        if widget_type == "checkbox"
        else "group"
        if widget_type in GROUP_WIDGETS
        else "stacked"
    )
    return {
        "field": bound_field,
        "widget": bound_field.as_widget(attrs=attrs),
        "help_id": help_id,
        "error_id": error_id,
        "layout": layout,
    }


SORT_ICONS = {"ascending": "arrow-up", "descending": "arrow-down", "": "chevrons-up-down"}


@register.simple_tag(takes_context=True)
def sort_th(context: Context, label: str, key: str, css_class: str = "") -> SafeString:
    """A sortable column header: ?sort=key ascending, ?sort=-key descending (spec §12).

    The link's id (sort-<key>) is stable, so htmx puts focus back on it after the table is swapped.
    """
    request = context["request"]
    current = request.GET.get("sort") or context.get("default_sort", "")
    query = request.GET.copy()
    query.pop("page", None)
    if current == key:
        query["sort"], direction = f"-{key}", "ascending"
    elif current == f"-{key}":
        query["sort"], direction = key, "descending"
    else:
        query["sort"], direction = key, ""
    return format_html(
        '<th scope="col"{}{}><a class="sort" id="sort-{}" href="?{}">{}{}</a></th>',
        format_html(' class="{}"', css_class) if css_class else "",
        format_html(' aria-sort="{}"', direction) if direction else "",
        key,
        query.urlencode(),
        label,
        icon(SORT_ICONS[direction]),
    )


@register.inclusion_tag("components/pagination.html", takes_context=True)
def pagination(context: Context, page: Page[object]) -> dict[str, object]:
    return {"page": page, "request": context["request"]}
