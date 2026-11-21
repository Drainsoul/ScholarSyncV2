"""Demo samples for the M11 screens: notifications, tasks, support and the applications chart.

Every step is idempotent, so `load_demo` can run again without adding anything.
"""

from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.programs.models import Program
from apps.workspace import reply_templates, support, tasks
from apps.workspace.models import Notification, ReplyTemplate, SupportRequest, Task

TASKS = (
    ("Call the TCU registrar about enrolment confirmations", -2, False),
    ("Prepare the claim day checklist", 0, False),
    ("Check last semester's grade slips", -5, True),
)
# (topic, message, program slug or None, the office's in-app answer or None for an open one)
SUPPORT = (
    (
        SupportRequest.Topic.APPLICATION,
        "How long does the review of a LANI application usually take?",
        None,
        None,
    ),
    (
        SupportRequest.Topic.ACCOUNT,
        "Can I change the email address on my account?",
        None,
        "Not from the app yet. Send us a message here with the new address and we'll "
        "change it for you.",
    ),
    (
        SupportRequest.Topic.ALLOWANCE,
        "When is the next CEAA allowance release?",
        "tcu-ceaa",
        None,
    ),
)
# The office's starting texts for replies (rev 35): (title, topic, body).
REPLY_TEMPLATES = (
    (
        "We're looking into it",
        "",  # any topic
        "Hi {first_name}, thank you for your message. {program} is looking into it and will "
        "reply here as soon as we can.",
    ),
    (
        "Allowance release dates",
        SupportRequest.Topic.ALLOWANCE,
        "Hi {first_name}, {program} announces each release day on your Scholarships page and "
        "in your notifications. You'll see the date, time and place there as soon as it is set.",
    ),
    (
        "Application review time",
        SupportRequest.Topic.APPLICATION,
        "Hi {first_name}, reviews usually take two to three weeks after the window closes. "
        "We'll email you as soon as {program} decides.",
    ),
)
# Days before today for back-dated sample applications, so the chart has history.
BACK_DATES = (40, 70, 100)


def _user(email: str) -> User | None:
    return User.objects.filter(email__iexact=email).first()


def _read_older_notifications() -> None:
    """Carmela's allowance was approved, then released: the older notice reads as seen."""
    carmela = _user("scholar@scholarsync.test")
    if carmela is None:
        return
    rows = list(Notification.objects.filter(recipient=carmela).order_by("-created_at", "-pk"))
    older = [row.pk for row in rows[1:] if row.read_at is None]
    Notification.objects.filter(pk__in=older).update(read_at=timezone.now())


def _give_staff_tasks() -> None:
    staff = _user("staff@scholarsync.test")
    program = Program.objects.filter(slug="tcu-ceaa").first()
    if staff is None or program is None:
        return
    today = timezone.localdate()
    for title, offset, done in TASKS:
        if Task.objects.filter(owner=staff, title=title).exists():
            continue
        task = tasks.create_task(
            actor=staff,
            program=program,
            title=title,
            notes="",
            due_on=today + timedelta(days=offset),
        )
        if done:
            tasks.set_done(actor=staff, task=task, done=True)


def _give_student_support() -> None:
    student = _user("student@scholarsync.test")
    office = _user("office@scholarsync.test")
    if student is None or office is None:
        return
    for topic, message, slug, answer in SUPPORT:
        row = SupportRequest.objects.filter(sender=student, topic=topic).first()
        if row is None:
            program = Program.objects.filter(slug=slug).first() if slug else None
            row = support.send(
                sender=student, topic=topic, program=program, message=message, now=timezone.now()
            )
        if answer and not row.replies.exists():
            support.reply(
                actor=office, request_row=row, body=answer, template=None, now=timezone.now()
            )


def _give_reply_templates() -> None:
    office = _user("office@scholarsync.test")
    if office is None:
        return
    for title, topic, body in REPLY_TEMPLATES:
        if ReplyTemplate.objects.filter(title=title).exists():
            continue
        reply_templates.create_template(
            actor=office, title=title, topic=topic, program=None, subject="", body=body
        )


def _back_date_decided_applications() -> None:
    """Spread the decided (and returned) samples over earlier months for the chart.

    This back-dates sample rows with the ORM. Waiting applications are left alone, so the queue
    order and its "n of m waiting" pager stay as the review samples built them."""
    today = timezone.now()
    rows = Application.objects.filter(
        program__slug="tcu-ceaa",
        first_submitted_at__isnull=False,
        status__in=[
            Application.Status.APPROVED,
            Application.Status.REJECTED,
            Application.Status.WITHDRAWN,
            Application.Status.RETURNED,
        ],
    ).order_by("pk")
    for index, row in enumerate(rows):
        when = today - timedelta(days=BACK_DATES[index % len(BACK_DATES)])
        Application.objects.filter(pk=row.pk).update(first_submitted_at=when)


def give_workspace_samples() -> None:
    _read_older_notifications()
    _give_staff_tasks()
    _give_student_support()
    _give_reply_templates()
    _back_date_decided_applications()
