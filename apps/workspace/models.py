from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual


class EmailOutbox(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    to = models.EmailField()
    kind = models.CharField(max_length=64)
    context = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"


class Notification(models.Model):
    """A message for one user in the app. Title, body and url are app-written, never free text."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=200, blank=True)  # site-relative path
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self) -> str:
        return f"{self.kind} #{self.pk}"


class Task(models.Model):
    """A personal to-do of one staff member in one program. Only the owner ever sees it."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    program = models.ForeignKey(
        "programs.Program", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    due_on = models.DateField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("notes"), 2000), name="workspace_task_notes_len"
            )
        ]
        indexes = [models.Index(fields=["owner", "program", "done_at"])]

    def __str__(self) -> str:
        return f"Task #{self.pk}"
