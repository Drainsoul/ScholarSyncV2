from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, Request, expect

from apps.accounts.tests.factories import UserFactory
from tests.e2e.flows import log_in, one_kb_pdf, payload

pytestmark = pytest.mark.e2e

KIT_UPLOAD = "/_kit/demo/upload/"
MB = 1024 * 1024
CONFIRM_400 = "Failed to load resource: the server responded with a status of 400"


def sign_in_to_the_upload_page(page: Page, live_server) -> None:
    user = UserFactory.create(verified=True)
    log_in(page, live_server.url, user.email, KIT_UPLOAD)
    expect(page.get_by_role("heading", level=1)).to_have_text("Try uploads")


def record_upload_requests(page: Page) -> list[str]:
    seen: list[str] = []

    def on_request(request: Request) -> None:
        if "/files/uploads/" in request.url:
            seen.append(request.url)

    page.on("request", on_request)
    return seen


def document_control(page: Page) -> Locator:
    return page.get_by_label("Supporting document", exact=True)


def document_field(page: Page) -> Locator:
    return page.locator(".file-input").filter(has=document_control(page))


def test_upload_pdf_then_download(page: Page, live_server, vite_build, e2e_storage, console_errors):
    sign_in_to_the_upload_page(page, live_server)
    body = one_kb_pdf()
    document_control(page).set_input_files(files=payload("grades.pdf", "application/pdf", body))
    field = document_field(page)
    expect(field.locator(".file-input__status")).to_have_text("grades.pdf uploaded")
    expect(field.locator("[data-upload-live]")).to_have_text("grades.pdf uploaded")
    assert field.locator("[data-upload-value]").input_value() != ""

    page.reload()
    link = page.get_by_role("link", name="grades.pdf")
    expect(link).to_be_visible()
    with page.expect_download() as info:
        link.click()
    download = info.value
    assert Path(download.path()).read_bytes() == body
    assert console_errors == []


def test_wrong_type_is_caught_before_any_request(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    sign_in_to_the_upload_page(page, live_server)
    requests = record_upload_requests(page)
    document_control(page).set_input_files(files=payload("notes.txt", "text/plain", b"hello"))
    field = document_field(page)
    expect(field.locator(".field__error")).to_have_text(
        "You can upload a PDF, JPG or PNG file here."
    )
    expect(document_control(page)).to_have_attribute("aria-invalid", "true")
    assert requests == []
    assert console_errors == []


def test_too_large_is_caught_before_any_request(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    sign_in_to_the_upload_page(page, live_server)
    requests = record_upload_requests(page)
    document_control(page).set_input_files(
        files=payload("big.pdf", "application/pdf", b"0" * (10 * MB + 1))
    )
    expect(document_field(page).locator(".field__error")).to_have_text(
        "This file is 11 MB. Upload a file of 10 MB or less."
    )
    assert requests == []
    assert console_errors == []


def test_fake_pdf_is_rejected_by_the_server(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    sign_in_to_the_upload_page(page, live_server)
    control = document_control(page)
    control.set_input_files(files=payload("fake.pdf", "application/pdf", b"just some text"))
    field = document_field(page)
    expect(field.locator(".field__error")).to_have_text("This isn't a valid PDF, JPG or PNG file.")
    expect(control).to_have_attribute("aria-invalid", "true")
    expect(control).to_have_attribute("aria-describedby", "kit-document-help kit-document-error")
    expect(field.locator("[data-upload-live]")).to_have_text(
        "This isn't a valid PDF, JPG or PNG file."
    )
    assert field.locator("[data-upload-value]").input_value() == ""
    # Chromium logs every 4xx fetch; the confirm's 400 is the expected answer, nothing else may log.
    assert [error for error in console_errors if not error.startswith(CONFIRM_400)] == []


def test_done_state_has_no_native_file_text(
    page: Page, live_server, vite_build, e2e_storage, console_errors
):
    sign_in_to_the_upload_page(page, live_server)
    document_control(page).set_input_files(
        files=payload("grades.pdf", "application/pdf", one_kb_pdf())
    )
    field = document_field(page)
    expect(field.locator(".file-input__status")).to_have_text("grades.pdf uploaded")
    expect(field.locator(".file-input__status svg use")).to_have_count(1)
    expect(field.locator(".file-input__control")).to_be_hidden()
    replace = field.get_by_role("button", name="Replace file")
    expect(replace).to_be_visible()
    replace.focus()
    expect(replace).to_be_focused()
    expect(field.locator(".file-input__nojs")).to_be_hidden()

    first_id = field.locator("[data-upload-value]").input_value()
    with page.expect_file_chooser() as chooser:
        replace.click()
    chooser.value.set_files(files=payload("grades-2.pdf", "application/pdf", one_kb_pdf()))
    expect(field.locator(".file-input__status")).to_have_text("grades-2.pdf uploaded")
    assert field.locator("[data-upload-value]").input_value() not in ("", first_id)
    assert console_errors == []
