from decimal import Decimal

import pytest
from django.template import Context, Template

from apps.core.templatetags.ui import peso


def render(source: str, **context) -> str:
    return Template("{% load ui %}" + source).render(Context(context))


def test_icon_is_decorative_by_default():
    assert render('{% icon "check" %}') == (
        '<svg class="icon" aria-hidden="true" focusable="false">'
        '<use href="/static/dist/icons.svg#check"></use></svg>'
    )


def test_icon_with_a_label_is_announced():
    html = render('{% icon "check" "Approved" %}')
    assert 'role="img" aria-label="Approved"' in html
    assert "aria-hidden" not in html


def test_icon_label_is_escaped():
    assert "&lt;b&gt;" in render('{% icon "check" label %}', label="<b>")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1234.5"), "₱1,234.50"),
        (0, "₱0.00"),
        (Decimal("-50"), "-₱50.00"),
        (Decimal("0.005"), "₱0.01"),
        (Decimal("-0.001"), "₱0.00"),
        (Decimal("1000000"), "₱1,000,000.00"),
        (None, "—"),
    ],
)
def test_peso(value, expected):
    assert render("{{ value|peso }}", value=value) == expected


def test_peso_rejects_floats():
    with pytest.raises(TypeError, match="Decimal"):
        peso(0.1)  # type: ignore[arg-type]
