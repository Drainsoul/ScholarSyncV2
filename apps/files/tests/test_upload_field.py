import re

import pytest
from django.template import Context, Template, TemplateSyntaxError

from apps.accounts.tests.factories import UserFactory
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory


def render(source: str) -> str:
    return Template("{% load uploads %}" + source).render(Context())


def test_photo_field_carries_the_upload_attributes():
    html = render('{% upload_field "photo" "pic" "pic" "Photo" %}')
    assert 'data-upload-purpose="photo"' in html
    assert 'data-upload-url="/files/uploads/"' in html
    assert f'data-upload-max="{5 * 1024 * 1024}"' in html
    assert 'accept="image/jpeg,image/png"' in html
    assert "JPG or PNG, up to 5 MB." in html


def test_file_control_has_no_name_and_a_hidden_input_carries_the_id():
    html = render('{% upload_field "document" "doc" "doc-name" "Supporting document" %}')
    control = re.search(r'<input class="file-input__control"[^>]*>', html)
    assert control
    assert " name=" not in control.group(0)
    assert re.search(r'<input type="hidden" name="doc-name" data-upload-value>', html)
    assert 'role="status" data-upload-live' in html
    assert "data-upload-replace hidden" in html
    assert "Uploading files needs JavaScript. Turn it on and reload the page." in html


def test_custom_help_wins():
    html = render('{% upload_field "photo" "p" "p" "Photo" help="Face the camera." %}')
    assert "Face the camera." in html
    assert "JPG or PNG, up to 5 MB." not in html


def test_unknown_purpose_raises():
    with pytest.raises(TemplateSyntaxError):
        render('{% upload_field "video" "v" "v" "Video" %}')


INCLUDE = '{% include "components/file_input.html" with id="a" name="a" label="A" '


def test_static_done_state_shows_replace_and_hides_nothing_else():
    html = Template(INCLUDE + 'state="done" filename="x.pdf" %}').render(Context())
    assert "file-input--done" in html
    assert "data-upload-replace" in html
    assert "data-upload-replace hidden" not in html


def test_static_idle_state_keeps_replace_out():
    html = Template(INCLUDE + 'state="idle" %}').render(Context())
    assert "data-upload-replace" not in html
    assert "file-input--done" not in html


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_kit_upload_page_is_404_when_kit_is_off(client, settings):
    settings.KIT_ENABLED = False
    assert client.get("/_kit/demo/upload/").status_code == 404


@pytest.mark.django_db
def test_kit_upload_page_lists_only_the_users_ready_files(client, kit_on, vite_build):
    user = UserFactory(verified=True)
    ready = {
        "status": StoredFile.Status.READY,
        "sniffed_type": "application/pdf",
        "sha256": "a" * 64,
    }
    StoredFileFactory(uploaded_by=user, original_name="mine.pdf", size=2048, **ready)
    StoredFileFactory(uploaded_by=user, original_name="pending.pdf")
    StoredFileFactory(original_name="theirs.pdf", **ready)
    client.force_login(user)
    body = client.get("/_kit/demo/upload/").content.decode()
    assert "Supporting document" in body
    assert 'id="kit-photo"' in body
    assert "mine.pdf" in body
    assert "2.0\xa0KB" in body
    assert "pending.pdf" not in body
    assert "theirs.pdf" not in body


@pytest.mark.django_db
def test_kit_upload_page_empty_list(client, kit_on, vite_build):
    client.force_login(UserFactory(verified=True))
    assert "No files yet." in client.get("/_kit/demo/upload/").content.decode()


@pytest.mark.django_db
def test_kit_upload_page_anonymous_sees_sign_in(client, kit_on, vite_build):
    body = client.get("/_kit/demo/upload/").content.decode()
    assert "Sign in to try uploads." in body
    assert "next=/_kit/demo/upload/" in body
    assert "data-upload-purpose" not in body
