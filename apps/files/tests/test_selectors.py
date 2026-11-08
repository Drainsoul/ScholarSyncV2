import pytest

from apps.accounts.tests.factories import UserFactory
from apps.files.selectors import usable_file
from apps.files.tests.factories import StoredFileFactory

READY = {"status": "ready", "sha256": "a" * 64, "sniffed_type": "image/png"}


@pytest.mark.django_db
def test_usable_file_rules() -> None:
    me = UserFactory.create(verified=True)
    good = StoredFileFactory.create(uploaded_by=me, purpose="photo", **READY)
    assert usable_file(me, str(good.id), "photo") == good
    assert usable_file(me, good.id, "photo") == good
    for bad in [
        StoredFileFactory.create(purpose="photo", **READY),
        StoredFileFactory.create(uploaded_by=me, purpose="photo"),
        StoredFileFactory.create(uploaded_by=me, purpose="document", **READY),
    ]:
        assert usable_file(me, str(bad.id), "photo") is None


@pytest.mark.django_db
@pytest.mark.parametrize("junk", ["not-a-uuid", "", None, 123, object()])
def test_usable_file_never_raises(junk: object) -> None:
    me = UserFactory.create(verified=True)
    assert usable_file(me, junk, "photo") is None
