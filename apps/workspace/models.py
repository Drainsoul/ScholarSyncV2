from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual


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


class SupportRequest(models.Model):
    """A student's message to the scholarship office. The office replies by email."""

    class Topic(models.TextChoices):
        ACCOUNT = "account", "My account"
        PROFILE = "profile", "My profile"
        APPLICATION = "application", "An application"
        ALLOWANCE = "allowance", "An allowance"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Waiting"
        ANSWERED = "answered", "Answered"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_requests"
    )
    topic = models.CharField(max_length=12, choices=Topic)
    program = models.ForeignKey(
        "programs.Program", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    message = models.TextField()
    status = models.CharField(max_length=10, choices=Status, default=Status.OPEN)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("message"), 2000)
                & GreaterThanOrEqual(Length("message"), 1),
                name="workspace_support_message_len",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Support request #{self.pk}"


class ReplyTemplate(models.Model):
    """A starting text for a support reply, kept by the office (spec §4.8 rev 35)."""

    title = models.CharField(max_length=80)
    topic = models.CharField(max_length=12, choices=SupportRequest.Topic, blank=True)  # blank: any
    program = models.ForeignKey(
        "programs.Program", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    subject = models.CharField(max_length=150, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("body"), 4000)
                & GreaterThanOrEqual(Length("body"), 1),
                name="workspace_template_body_len",
            ),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length("title"), 1),
                name="workspace_template_title_len",
            ),
            models.UniqueConstraint(
                fields=["title"],
                condition=Q(is_active=True),
                name="workspace_template_active_title",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class SupportReply(models.Model):
    """An answer to a support request, in the app or by email. Final: never edited."""

    class Channel(models.TextChoices):
        APP = "app", "In the app"
        EMAIL = "email", "By email"

    request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    channel = models.CharField(max_length=5, choices=Channel)
    subject = models.CharField(max_length=150, blank=True)
    body = models.TextField()
    template = models.ForeignKey(
        ReplyTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    email = models.ForeignKey(
        EmailOutbox, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("body"), 4000)
                & GreaterThanOrEqual(Length("body"), 1),
                name="workspace_reply_body_len",
            ),
            models.CheckConstraint(
                condition=(Q(channel="app") & Q(subject=""))
                | (Q(channel="email") & GreaterThanOrEqual(Length("subject"), 1)),
                name="workspace_reply_subject_by_channel",
            ),
        ]

    def __str__(self) -> str:
        return f"Reply {self.pk} ({self.channel})"
