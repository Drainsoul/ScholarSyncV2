import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


def pending_key(file_id: uuid.UUID) -> str:
    return f"pending/{file_id}"


class StoredFile(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        REJECTED = "rejected", "Rejected"

    class Purpose(models.TextChoices):
        DOCUMENT = "document", "Document"
        PHOTO = "photo", "Photo"
        REPORT = "report", "Report"
        EXPORT = "export", "Export"
        IMPORT = "import", "Import"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    purpose = models.CharField(max_length=10, choices=Purpose, default=Purpose.DOCUMENT)
    original_name = models.CharField(max_length=255)
    declared_type = models.CharField(max_length=100)
    sniffed_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True)
    rejected_reason = models.CharField(max_length=32, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "ready", "rejected"]),
                name="storedfile_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(purpose__in=["document", "photo", "report", "export", "import"]),
                name="storedfile_purpose_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status="ready") | (~Q(sha256="") & ~Q(sniffed_type="")),
                name="storedfile_ready_has_hash_and_type",
            ),
            models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(rejected_reason=""),
                name="storedfile_rejected_has_reason",
            ),
        ]
        indexes = [models.Index(fields=["uploaded_by", "status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.purpose} {self.id} ({self.status})"

    @property
    def final_key(self) -> str:
        return f"files/{self.purpose}/{self.id}"
