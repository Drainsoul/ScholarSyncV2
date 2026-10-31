from django.template import Context, Template


def test_include_if_present_renders_an_existing_template():
    out = Template('{% load slots %}{% include_if_present "components/empty_state.html" %}').render(
        Context({"title": "Nothing here yet"})
    )
    assert "Nothing here yet" in out


def test_include_if_present_is_empty_for_a_missing_template():
    out = Template('{% load slots %}[{% include_if_present "nope/missing.html" %}]').render(
        Context()
    )
    assert out == "[]"
