"""Audit events as short sentences for the office ("Krista Kelley approved a payout (TCU CEAA)").

Audit data never holds names (spec §9) and a student actor reads "A student", so no sentence
names a student. Only actions with a verb here appear in the recent-activity feed: file views,
profile edits and sign-ins would drown it.
"""

from datetime import datetime

from django.utils import timezone

from apps.accounts.models import User

from .models import AuditEvent

VERBS: dict[str, str] = {
    "application.submitted": "submitted an application",
    "application.resubmitted": "sent an application back in",
    "application.withdrawn": "withdrew an application",
    "application.approved": "approved an application",
    "application.returned": "returned an application",
    "application.rejected": "turned down an application",
    "application.expired": "closed an unfinished application",
    "application.started_on_behalf": "started an application for a student",
    "award.created": "added a scholar",
    "award.status_changed": "changed a scholar's status",
    "scholars.imported": "imported scholars",
    "disbursements.generated": "prepared payouts",
    "disbursement.approved": "approved a payout",
    "disbursement.rejected": "turned down a payout",
    "disbursement.released": "released a payout",
    "disbursement.reverted": "reverted a payout",
    "schedule.created": "added a distribution day",
    "schedule.published": "published a distribution day",
    "budget.set": "set the budget",
    "term.made_current": "moved the current term",
    "term.year_added": "added a school year",
    "invite.sent": "invited a student",
    "profile.created_by_staff": "added a student profile",
    "support.sent": "sent the office a message",
    "support.answered": "answered a support request",
    "report.submitted": "sent the office a report",
    "report.resubmitted": "sent a report back to the office",
    "report.accepted": "accepted a report",
    "report.returned": "returned a report",
}
# The overview's recent activity: the actions above. Settings, profile edits, file views and
# sign-ins would drown it; the audit log (VERBS below) reads every action.
FEED_ACTIONS: frozenset[str] = frozenset(VERBS)

VERBS.update(
    {
        "application.started": "started an application",
        "application.renewal_started": "started a renewal",
        "application.review_started": "started reviewing an application",
        "application.academics_set": "filled in the academics on an application",
        "award.updated": "edited a scholar",
        "scholar_term.created": "added a term record",
        "scholar_term.updated": "edited a term record",
        "scholar_term.merit_confirmed": "confirmed merit on a term record",
        "scholars.exported": "downloaded a scholar list",
        "analytics.exported": "downloaded the program summary",
        "document.uploaded": "uploaded a document",
        "document.approved": "approved a document",
        "document.declined": "declined a document",
        "document.added": "added a required document",
        "document.updated": "edited a required document",
        "document.stopped": "stopped asking for a document",
        "document.restored": "asked for a document again",
        "schedule.updated": "edited a distribution day",
        "schedule.unpublished": "unpublished a distribution day",
        "program.created": "created a program",
        "program.updated": "edited a program",
        "program.activated": "opened a program",
        "program.deactivated": "closed a program",
        "program.rules_changed": "changed a program's rules",
        "tier.added": "added an allowance tier",
        "tier.changed": "changed an allowance tier's amounts",
        "tier.stopped": "stopped offering an allowance tier",
        "school.added": "added a school",
        "school.updated": "edited a school",
        "user.signed_up": "signed up",
        "user.signed_in": "signed in",
        "user.signed_out": "signed out",
        "user.sign_in_failed": "failed to sign in",
        "user.created": "created an account",
        "user.promoted": "promoted an account",
        "user.deactivated": "deactivated an account",
        "user.reactivated": "reactivated an account",
        "user.email_confirmed": "confirmed an email address",
        "user.password_changed": "changed a password",
        "user.password_reset": "reset a password",
        "user.password_set": "set a password",
        "consent.recorded": "agreed to the privacy notice",
        "membership.added": "added a program membership",
        "membership.changed": "changed a program membership",
        "membership.removed": "removed a program membership",
        "mfa.removed": "removed an account's two-factor sign-in",
        "profile.created": "started a profile",
        "profile.updated": "edited a profile",
        "profile.claimed": "claimed a profile",
        "profile.imported": "added a student profile by import",
        "profile.photo_set": "set a profile photo",
        "profile.photo_removed": "removed a profile photo",
        "family.added": "added a family member",
        "family.updated": "edited a family member",
        "family.removed": "removed a family member",
        "education.added": "added education",
        "education.updated": "edited education",
        "education.removed": "removed education",
        "file.upload_started": "started an upload",
        "file.uploaded": "uploaded a file",
        "file.rejected": "had an upload turned down",
        "file.viewed": "downloaded a file",
        "task.created": "added a task",
        "task.updated": "edited a task",
        "task.completed": "finished a task",
        "task.reopened": "reopened a task",
        "task.deleted": "deleted a task",
    }
)

# The audit log's "What" filter: a group of action prefixes (the part before the dot).
AUDIT_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "applications": ("Applications", ("application",)),
    "documents": ("Documents", ("document",)),
    "scholars": ("Scholars", ("award", "scholar_term", "scholars")),
    "money": ("Money", ("disbursement", "disbursements", "schedule", "budget")),
    "terms": ("Terms", ("term",)),
    "programs": ("Programs and settings", ("program", "tier")),
    "schools": ("Schools", ("school",)),
    "accounts": ("Accounts", ("user", "membership", "consent", "mfa")),
    "profiles": ("Student profiles", ("profile", "invite", "family", "education")),
    "reports": ("Reports and analytics", ("report", "analytics")),
    "support": ("Support", ("support",)),
    "files": ("Files", ("file",)),
    "tasks": ("Tasks", ("task",)),
}

FEED_SIZE = 8


def actor_name(actor: User | None) -> str:
    if actor is None:
        return "The system"
    if actor.role == User.Role.STUDENT:
        return "A student"
    return actor.full_name or "A staff member"


def describe(event: AuditEvent) -> str:
    who = actor_name(event.actor)
    if event.actor is None and event.action == "user.sign_in_failed":
        who = "Someone"
    verb = VERBS.get(event.action)
    if verb is None:
        return f"{who}: {event.action}"
    suffix = f" ({event.program.name})" if event.program is not None else ""
    return f"{who} {verb}{suffix}"


def recent_activity(limit: int = FEED_SIZE) -> list[tuple[AuditEvent, str]]:
    """The latest events that read as a sentence, newest first."""
    events = (
        AuditEvent.objects.filter(action__in=sorted(FEED_ACTIONS))
        .select_related("actor", "program")
        .order_by("-at", "-pk")[:limit]
    )
    return [(event, describe(event)) for event in events]


def when(moment: datetime) -> str:
    """ "Today, 9:40 AM", "Yesterday, 4:12 PM" or "25 Oct, 11:03 AM", in Manila time."""
    local = timezone.localtime(moment)
    today = timezone.localdate()
    clock = f"{local:%I:%M %p}".lstrip("0")
    days = (today - local.date()).days
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Yesterday, {clock}"
    return f"{local.day} {local:%b}, {clock}"
