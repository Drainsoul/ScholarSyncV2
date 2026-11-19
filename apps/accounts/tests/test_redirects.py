"""Where the emailed account links land once they are followed to the end."""

import re
from typing import Any

from django.urls import reverse

from apps.accounts.tests.factories import UserFactory

SIGNUP = {
    "full_name": "Ana Cruz",
    "email": "ana@scholarsync.test",
    "password1": "signup-pass-2026",
    "password2": "signup-pass-2026",
    "consent": "on",
}


def _link(body: str, path: str) -> str:
    match = re.search(rf"https?://[^/\s]+({re.escape(path)}\S+)", body)
    assert match, body
    return match.group(1)


def test_confirming_the_signup_email_signs_the_student_in_at_their_home(
    client: Any, db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/accounts/signup/", SIGNUP)
    link = _link(mailoutbox[0].body, "/accounts/confirm-email/")
    assert client.get(link).status_code == 200
    response = client.post(link)
    assert response.status_code == 302 and response.url == reverse("students:home")
    assert "_auth_user_id" in client.session


def test_confirming_an_email_from_another_browser_goes_to_the_sign_in_page(
    client: Any, db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/accounts/signup/", SIGNUP)
    link = _link(mailoutbox[0].body, "/accounts/confirm-email/")
    client.cookies.clear()
    response = client.post(link)
    assert response.status_code == 302 and response.url == reverse("account_login")


def test_a_password_reset_ends_on_a_page_that_links_to_sign_in(
    client: Any, db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    UserFactory.create(email="ana@scholarsync.test", verified=True)
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/accounts/password/reset/", {"email": "ana@scholarsync.test"})
    link = _link(mailoutbox[0].body, "/accounts/password/reset/key/")
    response = client.get(link)
    assert response.status_code == 302  # allauth moves the key into the session
    form_url = response.url
    response = client.post(
        form_url, {"password1": "reset-pass-2026-x", "password2": "reset-pass-2026-x"}
    )
    assert response.status_code == 302
    assert response.url == reverse("account_reset_password_from_key_done")
    page = client.get(response.url).content.decode()
    assert f'href="{reverse("account_login")}"' in page


def test_the_check_your_email_pages_link_back_to_sign_in(
    client: Any, db: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        sent = client.post("/accounts/signup/", SIGNUP, follow=True)
    client.cookies.clear()
    reset = client.post("/accounts/password/reset/", {"email": "ana@scholarsync.test"}, follow=True)
    for response in (sent, reset):
        assert response.status_code == 200
        assert f'href="{reverse("account_login")}"' in response.content.decode()
