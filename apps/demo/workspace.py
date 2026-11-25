"""Demo samples for the M11 screens: notifications, tasks, support (with reply templates, rev 35
and 36) and the applications chart.

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
# rev 36: messages from other sample students, so the CEAA and LANI inboxes have more to answer:
# (sender, topic, message, program slug).
MORE_SUPPORT = (
    (
        "applicant4@scholarsync.test",
        SupportRequest.Topic.APPLICATION,
        "My application was returned. Which document do I need to upload again?",
        "tcu-ceaa",
    ),
    (
        "scholar@scholarsync.test",
        SupportRequest.Topic.ALLOWANCE,
        "Do I need to renew before I can claim this semester's allowance?",
        "tcu-ceaa",
    ),
    (
        "lani.applicant1@scholarsync.test",
        SupportRequest.Topic.APPLICATION,
        "I study at UP. Did I pick the right allowance tier for my school?",
        "lani",
    ),
    (
        "lani.applicant2@scholarsync.test",
        SupportRequest.Topic.PROFILE,
        "I moved to another barangay in Taguig. How do I update my address?",
        "lani",
    ),
)
# The office's starting texts for replies (rev 35; more in rev 36): (title, topic, program slug,
# subject, body). An empty topic fits any request, an empty program every program, and an empty
# subject falls back to the default one. {first_name} and {program} are filled in when picked.
REPLY_TEMPLATES = (
    (
        "We're looking into it",
        "",  # any topic
        "",
        "",
        "Hi {first_name}, thank you for your message. {program} is looking into it and will "
        "reply here as soon as we can.",
    ),
    (
        "Allowance release dates",
        SupportRequest.Topic.ALLOWANCE,
        "",
        "",
        "Hi {first_name}, {program} announces each release day on your Scholarships page and "
        "in your notifications. You'll see the date, time and place there as soon as it is set.",
    ),
    (
        "Application review time",
        SupportRequest.Topic.APPLICATION,
        "",
        "",
        "Hi {first_name}, reviews usually take two to three weeks after the window closes. "
        "We'll email you as soon as {program} decides.",
    ),
    (
        "Thanks for the update",
        "",
        "",
        "Thanks for the update",
        "Hi {first_name}, thank you for letting us know. We've noted it, and {program} will get "
        "back to you if we need anything else.",
    ),
    (
        "Changing your account email",
        SupportRequest.Topic.ACCOUNT,
        "",
        "Changing the email on your account",
        "Hi {first_name}, reply to this message with the new address you'd like to use. We'll "
        "change it and send a confirmation link to the new address. Until you open that link, "
        "keep signing in with your current email.",
    ),
    (
        "Signing in and passwords",
        SupportRequest.Topic.ACCOUNT,
        "",
        "Help signing in",
        'Hi {first_name}, on the sign-in page choose "Forgot your password?" and we\'ll email you '
        "a link to set a new one. The link works for a short time, so use it soon. If the email "
        "doesn't arrive, check your spam folder and then reply here.",
    ),
    (
        "Updating your profile",
        SupportRequest.Topic.PROFILE,
        "",
        "Updating your profile",
        "Hi {first_name}, you can change your address, school and family details yourself under "
        "Profile. If an application is already being reviewed, tell us what changed so "
        "{program} can check it against your documents.",
    ),
    (
        "Documents to upload again",
        SupportRequest.Topic.APPLICATION,
        "",
        "Documents for your {program} application",
        'Hi {first_name}, open your application to see the documents marked "Declined" and the '
        'reason for each. Use "Replace file" to upload a clear copy of each one, then press '
        '"Resubmit". {program} reviews it again from where we left off.',
    ),
    (
        "Application not approved",
        SupportRequest.Topic.APPLICATION,
        "",
        "About your {program} application",
        "Hi {first_name}, we're sorry your application wasn't approved this time. The reason is "
        "on your application page. You can apply again in the next application window if your "
        "situation changes.",
    ),
    (
        "Renewing your scholarship",
        SupportRequest.Topic.APPLICATION,
        "",
        "Renewing your {program} scholarship",
        "Hi {first_name}, you can renew from your Scholarships page while the renewal window is "
        "open. Have your certificate of registration and last term's grades ready. Your "
        "allowance for the term is prepared once the renewal is approved.",
    ),
    (
        "Claim day reminder",
        SupportRequest.Topic.ALLOWANCE,
        "",
        "Your {program} allowance",
        "Hi {first_name}, your allowance is ready to claim. Bring a valid ID on the release day "
        "shown on your Scholarships page, at the place given there.",
    ),
    (
        "Missed the claim day",
        SupportRequest.Topic.ALLOWANCE,
        "",
        "Claiming your {program} allowance",
        "Hi {first_name}, an allowance not claimed on the release day stays with {program}. "
        "Reply with a day that suits you this week and we'll tell you when and where to claim it.",
    ),
    (
        "Forwarded to the right office",
        SupportRequest.Topic.OTHER,
        "",
        "",
        "Hi {first_name}, thank you for your message. We've passed it to the office that handles "
        "this, and they'll contact you directly.",
    ),
    (
        "LANI allowance tiers",
        SupportRequest.Topic.APPLICATION,
        "lani",
        "Your LANI allowance tier",
        "Hi {first_name}, LANI's tier depends on your school and your grades. Students at a state "
        "or local university apply under SUC/LCU; private schools under Basic or a merit tier. "
        "If you picked another one, {program} sets the right tier when it approves.",
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


def _give_more_support() -> None:
    """Questions from the sample applicants and scholars, each to its program's inbox (rev 36).
    Skips senders the loader didn't make (no storage, summer) and requests already sent."""
    for email, topic, message, slug in MORE_SUPPORT:
        sender = _user(email)
        program = Program.objects.filter(slug=slug).first()
        if sender is None or program is None:
            continue
        if SupportRequest.objects.filter(sender=sender, topic=topic).exists():
            continue
        support.send(
            sender=sender, topic=topic, program=program, message=message, now=timezone.now()
        )


def _give_reply_templates() -> None:
    office = _user("office@scholarsync.test")
    if office is None:
        return
    for title, topic, slug, subject, body in REPLY_TEMPLATES:
        if ReplyTemplate.objects.filter(title=title).exists():
            continue
        program = Program.objects.filter(slug=slug).first() if slug else None
        if slug and program is None:
            continue
        reply_templates.create_template(
            actor=office, title=title, topic=topic, program=program, subject=subject, body=body
        )


def _back_date_decided_applications() -> None:
    """Spread the decided (and returned) samples over earlier months for the chart.

    This back-dates sample rows with the ORM. Waiting applications are left alone, so the queue
    order and its "n of m waiting" pager stay as the review samples built them."""
    today = timezone.now()
    rows = Application.objects.filter(
        program__slug__in=("tcu-ceaa", "lani"),  # rev 36: LANI's samples too
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
    _give_more_support()
    _give_reply_templates()
    _back_date_decided_applications()
