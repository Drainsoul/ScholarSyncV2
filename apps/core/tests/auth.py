"""Sign-in helpers for tests of screens that ask for the password again."""

from typing import Any

from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD


def reauthenticated(client: Any, user: User) -> Any:
    """Signed in, then past the password page, so the next five minutes need no password."""
    assert client.login(email=user.email, password=DEFAULT_PASSWORD)
    response = client.post(reverse("account_reauthenticate"), {"password": DEFAULT_PASSWORD})
    assert response.status_code == 302
    return client


def signed_in_long_ago(client: Any, user: User) -> Any:
    """Signed in with a session that never passed the password page: sensitive posts redirect."""
    assert client.login(email=user.email, password=DEFAULT_PASSWORD)
    session = client.session
    session.pop("account_authentication_methods", None)
    session.save()
    return client


def replay_after_password(client: Any, response: Any) -> Any:
    """Follow a redirect to the password page, post the password, and return the replay."""
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_reauthenticate"))
    return client.post(response.url, {"password": DEFAULT_PASSWORD})
