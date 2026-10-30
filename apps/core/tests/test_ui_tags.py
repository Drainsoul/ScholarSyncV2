from decimal import Decimal

import pytest
from django.template import Context, Template, TemplateSyntaxError

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


@pytest.mark.parametrize("tone", ["success", "warning", "info", "danger", "neutral"])
def test_status_renders_tone_and_text(tone):
    assert render("{% status tone 'Under review' %}", tone=tone) == (
        f'<span class="status status--{tone}">Under review</span>'
    )


@pytest.mark.parametrize("tone", ["", "tag", "primary", "success extra"])
def test_status_rejects_unknown_tones(tone):
    with pytest.raises(TemplateSyntaxError, match="tone"):
        render("{% status tone 'Active' %}", tone=tone)


def test_status_escapes_text():
    html = render("{% status 'danger' text %}", text="<b>Ended</b>")
    assert html == '<span class="status status--danger">&lt;b&gt;Ended&lt;/b&gt;</span>'


@pytest.mark.parametrize(
    ("index", "tone"), [(0, "red"), (1, "blue"), (2, "yellow"), (3, "red"), (7, "blue")]
)
def test_avatar_initials_and_tone_cycle(index, tone):
    assert render("{% avatar 'Daniel Montoya' index %}", index=index) == (
        f'<span class="avatar avatar--{tone}" aria-hidden="true">DM</span>'
    )


def test_avatar_uses_the_first_and_last_word():
    html = render("{% avatar '  maria de la  cruz ' 0 %}")
    assert html == '<span class="avatar avatar--red" aria-hidden="true">MC</span>'


def test_avatar_single_word_name():
    assert ">C</span>" in render("{% avatar 'Cher' 0 %}")


def test_avatar_large_size():
    assert render("{% avatar 'Daniel Montoya' 2 size='lg' %}") == (
        '<span class="avatar avatar--yellow avatar--lg" aria-hidden="true">DM</span>'
    )


def test_avatar_escapes_and_handles_an_empty_name():
    assert "&lt;" in render("{% avatar '<x y' 0 %}")
    assert render("{% avatar '' 0 %}") == (
        '<span class="avatar avatar--red" aria-hidden="true"></span>'
    )
