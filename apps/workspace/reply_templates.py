"""Reply templates the office keeps for support answers (spec §4.8 rev 35).

One set serves replies in the app and emails. A template is only a start: the picked text is
filled with `{first_name}` and `{program}` and then edited freely before it is sent.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.accounts.models import User
from apps.core.audit import record
from apps.programs.models import Program

from .models import ReplyTemplate, SupportRequest

TITLE_CLASH = "An active template already has this title."
EDITABLE = ("title", "topic", "program", "subject", "body")
ABOUT = {
    "account": "your account",
    "profile": "your profile",
    "application": "an application",
    "allowance": "an allowance",
    "other": "something else",
}


def _title_taken(title: str, exclude: int | None = None) -> bool:
    rows = ReplyTemplate.objects.filter(title=title, is_active=True)
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    return rows.exists()


@transaction.atomic
def create_template(
    *,
    actor: User,
    title: str,
    topic: str,
    program: Program | None,
    subject: str,
    body: str,
    request: HttpRequest | None = None,
) -> ReplyTemplate:
    if _title_taken(title):
        raise ValidationError(TITLE_CLASH)
    template = ReplyTemplate.objects.create(
        title=title,
        topic=topic,
        program=program,
        subject=subject,
        body=body,
        created_by=actor,
        updated_by=actor,
    )
    record(actor=actor, action="support_template.created", target=template, request=request)
    return template


@transaction.atomic
def update_template(
    *,
    actor: User,
    template: ReplyTemplate,
    request: HttpRequest | None = None,
    **fields: object,
) -> ReplyTemplate:
    changed = [
        name for name in EDITABLE if name in fields and getattr(template, name) != fields[name]
    ]
    if (
        "title" in changed
        and template.is_active
        and _title_taken(str(fields["title"]), template.pk)
    ):
        raise ValidationError(TITLE_CLASH)
    for name in changed:
        setattr(template, name, fields[name])
    template.updated_by = actor
    template.save()
    record(
        actor=actor,
        action="support_template.updated",
        target=template,
        data={"fields": changed},
        request=request,
    )
    return template


@transaction.atomic
def set_active(
    *, actor: User, template: ReplyTemplate, active: bool, request: HttpRequest | None = None
) -> ReplyTemplate:
    if template.is_active == active:
        return template
    if active and _title_taken(template.title, template.pk):
        raise ValidationError(TITLE_CLASH)
    template.is_active = active
    template.updated_by = actor
    template.save(update_fields=["is_active", "updated_by", "updated_at"])
    action = "support_template.activated" if active else "support_template.deactivated"
    record(actor=actor, action=action, target=template, request=request)
    return template


def picker(request_row: SupportRequest) -> list[ReplyTemplate]:
    """Active templates for the request's topic and program, topic-specific first, then by title."""
    rows = ReplyTemplate.objects.filter(
        Q(topic=request_row.topic) | Q(topic=""),
        Q(program_id=request_row.program_id) | Q(program=None),
        is_active=True,
    )
    return sorted(rows, key=lambda t: (t.topic == "", t.title.casefold(), t.pk))


def first_name(user: User) -> str:
    """The first word of the name; never the email address."""
    words = user.full_name.split()
    return words[0] if words else "there"


def default_subject(request_row: SupportRequest) -> str:
    return f"Re: your message about {ABOUT.get(request_row.topic, 'something else')}"


def _placeholders(text: str, request_row: SupportRequest) -> str:
    program = request_row.program.name if request_row.program else "the scholarship office"
    return text.replace("{first_name}", first_name(request_row.sender)).replace(
        "{program}", program
    )


def fill(template: ReplyTemplate, request_row: SupportRequest) -> tuple[str, str]:
    """The template's (subject, body) for this request; a blank subject gets the default."""
    subject = _placeholders(template.subject, request_row) or default_subject(request_row)
    return subject, _placeholders(template.body, request_row)
