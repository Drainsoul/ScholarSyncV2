"""How application statuses read on student and staff screens."""

from apps.applications.models import Application

APPLICATION_TONES: dict[str, str] = {
    Application.Status.DRAFT: "warning",
    Application.Status.RETURNED: "warning",
    Application.Status.SUBMITTED: "info",
    Application.Status.UNDER_REVIEW: "info",
    Application.Status.APPROVED: "success",
    Application.Status.REJECTED: "neutral",
    Application.Status.WITHDRAWN: "neutral",
}
