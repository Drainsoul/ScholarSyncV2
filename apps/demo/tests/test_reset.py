"""The public demo's nightly reset (branch `demo`, hosted demo design section 5.4)."""

from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.demo import loader, reset
from apps.demo.accounts import ACCOUNTS, PASSWORD
from apps.files.models import StoredFile
from apps.files.tests.conftest import moto_server, s3  # noqa: F401 (fixtures)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def public_demo(settings: Any) -> None:
    settings.PUBLIC_DEMO = True
    settings.DEMO_ACTIVE = True
    settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "apps.demo"]


def _keys(client: Any) -> set[str]:
    listing = client.list_objects_v2(Bucket=client.bucket)
    return {o["Key"] for o in listing.get("Contents", [])}


def test_reset_refuses_outside_public_demo(settings: Any, s3: Any) -> None:  # noqa: F811
    settings.PUBLIC_DEMO = False
    s3.put_object(Bucket=s3.bucket, Key="files/keep", Body=b"")
    user = UserFactory.create()
    with pytest.raises(RuntimeError, match="only in the public demo"):
        reset.reset()
    assert "files/keep" in _keys(s3)
    assert User.objects.filter(pk=user.pk).exists()


def test_reset_restores_clean_demo(public_demo: None, s3: Any) -> None:  # noqa: F811
    from apps.demo.lockdown import bypass

    with bypass():
        loader.load()
    visitor = UserFactory.create()
    s3.put_object(Bucket=s3.bucket, Key="pending/visitor-upload", Body=b"x")

    result = reset.reset()

    assert not User.objects.filter(pk=visitor.pk).exists()
    for account in ACCOUNTS:
        assert User.objects.get(email=account.email).check_password(PASSWORD)
    keys = _keys(s3)
    assert "pending/visitor-upload" not in keys
    assert {f.key for f in StoredFile.objects.all()} <= keys
    assert StoredFile.objects.exists()
    assert result.files_deleted >= 1
    assert result.accounts_created == len(ACCOUNTS)
    assert result.seconds >= 0


def test_reset_is_atomic(public_demo: None, s3: Any, monkeypatch: Any) -> None:  # noqa: F811
    """A failed load keeps yesterday's rows and the files they point at."""
    survivor = UserFactory.create()
    s3.put_object(Bucket=s3.bucket, Key="files/yesterday", Body=b"x")

    def broken_load() -> int:
        raise ValueError("load failed")

    monkeypatch.setattr(loader, "load", broken_load)
    with pytest.raises(ValueError, match="load failed"):
        reset.reset()
    assert User.objects.filter(pk=survivor.pk).exists()
    assert "files/yesterday" in _keys(s3)
