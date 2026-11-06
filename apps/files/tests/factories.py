import uuid

import factory

from apps.accounts.tests.factories import UserFactory
from apps.files.models import StoredFile, pending_key


class StoredFileFactory(factory.django.DjangoModelFactory[StoredFile]):
    class Meta:
        model = StoredFile

    id = factory.declarations.LazyFunction(uuid.uuid4)
    key = factory.declarations.LazyAttribute(lambda o: pending_key(o.id))
    status = StoredFile.Status.PENDING
    purpose = StoredFile.Purpose.DOCUMENT
    original_name = "grades.pdf"
    declared_type = "application/pdf"
    sniffed_type = ""
    size = 1024
    sha256 = ""
    rejected_reason = ""
    uploaded_by = factory.declarations.SubFactory(UserFactory, verified=True)
