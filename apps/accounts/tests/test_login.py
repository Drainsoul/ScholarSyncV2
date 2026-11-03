from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.models import AuditEvent
from apps.workspace.models import EmailOutbox


def _login(client: Any, email: str, password: str = DEFAULT_PASSWORD) -> Any:
    return client.post("/accounts/login/", {"login": email, "password": password})


def test_unverified_users_cannot_log_in(client: Any, db: Any) -> None:
    UserFactory.create(email="ana@scholarsync.test", verified=False)
    response = _login(client, "ana@scholarsync.test")
    assert response.status_code == 302 and response.url == "/accounts/confirm-email/"
    assert "_auth_user_id" not in client.session


def test_login_is_case_insensitive(client: Any, db: Any) -> None:
    user = UserFactory.create(email="ana@scholarsync.test", verified=True)
    response = _login(client, "ANA@Scholarsync.TEST")
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_logout_needs_post(client: Any, db: Any) -> None:
    client.force_login(UserFactory.create(verified=True))
    client.get("/accounts/logout/")
    assert "_auth_user_id" in client.session
    client.post("/accounts/logout/")
    assert "_auth_user_id" not in client.session


def test_password_reset_for_an_unknown_email_sends_nothing(
    client: Any, db: Any, mailoutbox: Any
) -> None:
    response = client.post("/accounts/password/reset/", {"email": "nobody@scholarsync.test"})
    assert response.status_code == 302
    assert EmailOutbox.objects.count() == 0 and mailoutbox == []


def test_password_reset_sends_the_key_through_the_outbox(
    client: Any, db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    UserFactory.create(email="ana@scholarsync.test", verified=True)
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/accounts/password/reset/", {"email": "ana@scholarsync.test"})
    assert EmailOutbox.objects.get().kind == "password_reset_key"
    assert "/accounts/password/reset/key/" in mailoutbox[0].body


def test_email_change_asks_to_reauthenticate_after_five_minutes(
    client: Any, db: Any, time_machine: Any
) -> None:
    UserFactory.create(email="ana@scholarsync.test", verified=True)
    _login(client, "ana@scholarsync.test")
    time_machine.move_to(timezone.now() + timedelta(minutes=6), tick=False)
    response = client.post("/accounts/email/", {"action_add": "", "email": "new@scholarsync.test"})
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_reauthenticate"))


def test_password_reset_and_change_are_audited(
    client: Any, db: Any, django_capture_on_commit_callbacks: Any
) -> None:
    from allauth.account.forms import default_token_generator
    from allauth.account.utils import user_pk_to_url_str

    user = UserFactory.create(email="ana@scholarsync.test", verified=True)
    key = f"{user_pk_to_url_str(user)}-{default_token_generator.make_token(user)}"
    with django_capture_on_commit_callbacks(execute=True):
        response = client.get(f"/accounts/password/reset/key/{key}/")
        client.post(
            response.url, {"password1": "another-pass-2026", "password2": "another-pass-2026"}
        )
    assert AuditEvent.objects.filter(action="user.password_reset", actor=user).exists()
    _login(client, "ana@scholarsync.test", "another-pass-2026")
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            "/accounts/password/change/",
            {
                "oldpassword": "another-pass-2026",
                "password1": "third-pass-2026-x",
                "password2": "third-pass-2026-x",
            },
        )
    assert AuditEvent.objects.filter(action="user.password_changed", actor=user).exists()


def test_repeated_failed_logins_are_rate_limited(client: Any, db: Any) -> None:
    user = UserFactory.create(email="ana@scholarsync.test", verified=True)
    for _ in range(5):
        _login(client, "ana@scholarsync.test", "wrong-password-1")
    _login(client, "ana@scholarsync.test")
    assert "_auth_user_id" not in client.session
    cache.clear()
    _login(client, "ana@scholarsync.test")
    assert client.session["_auth_user_id"] == str(user.pk)
