import uuid

from django.db.models import QuerySet
from django.http import Http404

from apps.accounts.models import User

from .models import StoredFile


def ready_files_for(user: User) -> QuerySet[StoredFile]:
    """The user's own ready files, newest first."""
    return StoredFile.objects.filter(uploaded_by=user, status=StoredFile.Status.READY).order_by(
        "-created_at"
    )


def usable_file(user: User, file_id: object, purpose: str) -> StoredFile | None:
    """The user's own ready file of this purpose, or None. Never raises on a bad id."""
    try:
        parsed = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    except ValueError:
        return None
    return StoredFile.objects.filter(
        pk=parsed, uploaded_by=user, status=StoredFile.Status.READY, purpose=purpose
    ).first()


def downloadable_file(user: User, file_id: uuid.UUID) -> StoredFile:
    """A ready file the user uploaded (or any, for the scholarship office); else Http404."""
    queryset = StoredFile.objects.filter(pk=file_id, status=StoredFile.Status.READY)
    if not user.is_super_admin:
        queryset = queryset.filter(uploaded_by=user)
    file = queryset.first()
    if file is None:
        raise Http404("No such file.")
    return file
