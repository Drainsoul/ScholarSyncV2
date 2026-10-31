"""Optional template slots. Load with {% load slots %}."""

from django import template
from django.template import Context, TemplateDoesNotExist
from django.template.loader import get_template
from django.utils.safestring import SafeString, mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def include_if_present(context: Context, template_name: str) -> SafeString:
    """Render a template with the current context, or nothing if it doesn't exist."""
    try:
        found = get_template(template_name)
    except TemplateDoesNotExist:
        return mark_safe("")  # noqa: S308
    rendered = found.render(dict(context.flatten()))  # type: ignore[arg-type]
    return mark_safe(rendered)  # noqa: S308
