import uuid

from django.db.models import QuerySet
from django.http import Http404

from apps.accounts.models import User
from apps.applications.selectors import staff_can_download, student_can_download
from apps.reports.selectors import staff_can_download_report

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
    """A ready file the user may download, by purpose (spec §7, M12):

    - `import`: nobody, the office included (the rows were read once, at import);
    - `report`: the office and active staff of the report's program, whoever uploaded it;
    - `document` and `photo`: the uploader, the office, staff of a submitted or on-behalf
      application's program, or the student whose application it is;
    - `export`: unused (exports are built in the request and never stored); a row would follow
      the document rules.
    """
    file = StoredFile.objects.filter(pk=file_id, status=StoredFile.Status.READY).first()
    if file is None or file.purpose == StoredFile.Purpose.IMPORT:
        raise Http404("No such file.")
    if file.purpose == StoredFile.Purpose.REPORT:
        if user.is_super_admin or staff_can_download_report(user, file):
            return file
        raise Http404("No such file.")
    if (
        user.is_super_admin
        or file.uploaded_by_id == user.pk
        or staff_can_download(user, file)
        or student_can_download(user, file)
    ):
        return file
    raise Http404("No such file.")
