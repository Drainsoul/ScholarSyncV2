from django import forms
from django.template import Context, Template


class ApplicantForm(forms.Form):
    full_name = forms.CharField(label="Full name", help_text="As on your school ID.")
    school = forms.ChoiceField(label="School", choices=[("tcu", "Taguig City University")])
    nickname = forms.CharField(label="Nickname", required=False)
    year_level = forms.ChoiceField(
        label="Year level", widget=forms.RadioSelect, choices=[("1", "1st year"), ("2", "2nd year")]
    )
    consent = forms.BooleanField(label="I agree to the privacy notice")


def render_field(form: forms.Form, name: str) -> str:
    return Template("{% load ui %}{% field f %}").render(Context({"f": form[name]}))


def test_help_text_is_linked_to_the_input():
    html = render_field(ApplicantForm(), "full_name")
    assert '<p class="field__help" id="id_full_name-help">As on your school ID.</p>' in html
    assert 'aria-describedby="id_full_name-help"' in html
    assert "aria-invalid" not in html
    assert '<span class="field__required">(required)</span>' in html


def test_errors_mark_the_input_invalid_and_are_linked():
    form = ApplicantForm(data={"full_name": ""})
    form.is_valid()
    html = render_field(form, "full_name")
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="id_full_name-help id_full_name-error"' in html
    assert 'id="id_full_name-error"' in html
    assert "This field is required." in html
    assert "field--invalid" in html


def test_optional_fields_have_no_marker_or_description():
    html = render_field(ApplicantForm(), "nickname")
    assert "(required)" not in html
    assert "aria-describedby" not in html


def test_user_input_in_errors_is_escaped():
    form = ApplicantForm(data={"school": "<img src=x onerror=alert(1)>"})
    form.is_valid()
    html = render_field(form, "school")
    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_checkbox_puts_the_input_before_its_label():
    html = render_field(ApplicantForm(), "consent")
    assert "field--check" in html
    assert html.index('type="checkbox"') < html.index("<label")


def test_radio_group_is_a_fieldset_with_a_legend():
    html = render_field(ApplicantForm(), "year_level").strip()
    assert html.startswith('<fieldset class="field field--group')
    assert '<legend class="field__label">Year level' in html
