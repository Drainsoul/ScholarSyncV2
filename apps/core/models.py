from typing import Any

from django.conf import settings
from django.db import models


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    """New rows may be created; existing rows can never be changed or removed in bulk."""

    def update(self, **kwargs: Any) -> int:
        raise ValueError("Audit events are append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("Audit events are append-only.")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ValueError("Audit events are append-only.")


class AuditEvent(models.Model):
    """Append-only record of a state change. Rows are never updated or deleted."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=64)
    program = models.ForeignKey(
        "programs.Program",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self) -> str:
        return f"{self.action} #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValueError("Audit events are append-only and cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("Audit events are append-only and cannot be deleted.")
