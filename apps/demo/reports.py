"""Demo samples for the M11c screens: TCU CEAA reports (accepted, returned, waiting for the
office, and a staff member's report waiting for the head, rev 33), so the office has one to
review, and the head has one to fix and one to approve. rev 36 adds older accepted CEAA reports
and a LANI set (accepted, returned by the office, waiting for the office, waiting for the LANI
head). Skipped when storage isn't configured; every step skips what already exists."""

import hashlib
import logging
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.files import storage
from apps.files.models import StoredFile
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import current_term
from apps.reports.models import Report
from apps.reports.services import (
    decide_report,
    head_approve_report,
    office_url,
    send_report_to_office,
    staff_url,
    submit_report,
)
from apps.workspace.models import Notification

from .accounts import ACCOUNTS
from .samples import SAMPLE_PDF

logger = logging.getLogger(__name__)

PDF_TYPE = "application/pdf"
RETURN_NOTE = "Please add the number of walk-in applications for the month."
FOR_HEAD_TITLE = "Scholar attendance summary"


def _user(email: str) -> User | None:
    return User.objects.filter(email__iexact=email).first()


def _report_file(user: User, name: str) -> StoredFile:
    """Put a sample PDF to storage and record it as a ready report file."""
    file_id = uuid.uuid4()
    key = f"files/{StoredFile.Purpose.REPORT}/{file_id}"
    storage.put(key=key, body=SAMPLE_PDF, content_type=PDF_TYPE)
    return StoredFile.objects.create(
        id=file_id,
        key=key,
        status=StoredFile.Status.READY,
        purpose=StoredFile.Purpose.REPORT,
        original_name=name,
        declared_type=PDF_TYPE,
        sniffed_type=PDF_TYPE,
        size=len(SAMPLE_PDF),
        sha256=hashlib.sha256(SAMPLE_PDF).hexdigest(),
        uploaded_by=user,
    )


def _through_head(report: Report, head: User) -> Report:
    """A staff member's report, approved by the head and sent to the office (rev 33)."""
    head_approve_report(actor=head, report=report, note="")
    return send_report_to_office(actor=head, report=report)


def _samples(program: Program, staff: User, head: User, office: User) -> None:
    term = current_term()
    if term is None:
        return
    previous = AcademicTerm.objects.filter(sort_key__lt=term.sort_key).order_by("-sort_key").first()
    if previous is None:
        return
    accepted = submit_report(
        actor=staff,
        program=program,
        title="Semester disbursement summary",
        period_start=previous.starts_on,
        period_end=previous.ends_on,
        description="Allowances released last semester, by tier.",
        file=_report_file(staff, "semester-disbursement-summary.pdf"),
    )
    accepted = _through_head(accepted, head)
    decide_report(actor=office, report=accepted, accept=True, note="")
    returned = submit_report(
        actor=head,
        program=program,
        title="Monthly applications report",
        period_start=term.starts_on,
        period_end=term.ends_on,
        description="Applications received, reviewed and approved this month.",
        file=_report_file(head, "monthly-applications-report.pdf"),
    )
    decide_report(actor=office, report=returned, accept=False, note=RETURN_NOTE)
    waiting = submit_report(
        actor=staff,
        program=program,
        title="Quarterly scholar update",
        period_start=term.starts_on,
        period_end=term.ends_on,
        description="Scholar counts and renewals this quarter.",
        file=_report_file(staff, "quarterly-scholar-update.pdf"),
    )
    waiting = _through_head(waiting, head)
    now = timezone.now()
    # Only the waiting report and the returned one read as new.
    Notification.objects.filter(recipient=office, kind="report_submitted").exclude(
        url=office_url(waiting)
    ).update(read_at=now)
    Notification.objects.filter(
        recipient__in=[staff, head], kind__in=["report_accepted", "report_head_approved"]
    ).update(read_at=now)
    Notification.objects.filter(recipient=head, kind="report_for_head").update(read_at=now)


def _for_head(program: Program, staff: User, head: User) -> None:
    """A staff member's report waiting for the head (rev 33); its notice to the head is new."""
    term = current_term()
    if term is None:
        return
    submit_report(
        actor=staff,
        program=program,
        title=FOR_HEAD_TITLE,
        period_start=term.starts_on,
        period_end=term.ends_on,
        description="Scholars who attended this term's orientation and check-ins.",
        file=_report_file(staff, "scholar-attendance-summary.pdf"),
    )


# rev 36: (program slug, sender: "staff" or "head", title, description, period, outcome). Period
# "previous" is the term before the current one. Outcome: accepted (through the head when staff
# sent it), returned (by the office), office (waiting for it) or head (waiting for the head).
MORE_REPORTS = (
    (
        "tcu-ceaa",
        "staff",
        "Renewal compliance checklist",
        "Scholars who handed in their grades and registration for renewal, by year level.",
        "previous",
        "accepted",
    ),
    (
        "tcu-ceaa",
        "head",
        "Budget utilization report",
        "Allowances paid against this year's budget, with the balance left.",
        "previous",
        "accepted",
    ),
    (
        "lani",
        "staff",
        "LANI applications summary",
        "Applications received and decided this term, by school and tier.",
        "previous",
        "accepted",
    ),
    (
        "lani",
        "head",
        "LANI school list update",
        "Schools our scholars attend this term, with their grading scales.",
        "current",
        "returned",
    ),
    (
        "lani",
        "head",
        "LANI tier breakdown",
        "Scholars and allowance amounts by tier for this term.",
        "current",
        "office",
    ),
    (
        "lani",
        "staff",
        "LANI scholar grade review",
        "Scholars whose grades are near the renewal mark, for an early check-in.",
        "current",
        "head",
    ),
)
LANI_RETURN_NOTE = "Please add the grading scale for the two new schools."


def _sender(slug: str, level: str) -> User | None:
    """The demo's staff or head account for a program (accounts.py)."""
    wanted = "head" if level == "head" else "staff"
    for account in ACCOUNTS:
        if account.program == slug and account.level == wanted:
            return _user(account.email)
    return None


def _more_samples(office: User) -> None:
    """The rev 36 reports, each skipped once its program has a report with its title. Notices
    stay new only for reports still waiting and for a head's returned one."""
    term = current_term()
    if term is None:
        return
    previous = AcademicTerm.objects.filter(sort_key__lt=term.sort_key).order_by("-sort_key").first()
    if previous is None:
        return
    decided: list[Report] = []
    for slug, level, title, description, period, outcome in MORE_REPORTS:
        program = Program.objects.filter(slug=slug, is_active=True).first()
        sender = _sender(slug, level)
        head = _sender(slug, "head")
        if program is None or sender is None or head is None:
            continue
        if Report.objects.filter(program=program, title=title).exists():
            continue
        span = previous if period == "previous" else term
        report = submit_report(
            actor=sender,
            program=program,
            title=title,
            period_start=span.starts_on,
            period_end=span.ends_on,
            description=description,
            file=_report_file(sender, f"{title.lower().replace(' ', '-')}.pdf"),
        )
        if outcome == "head":
            continue
        if level == "staff":
            report = _through_head(report, head)
        if outcome == "accepted":
            report = decide_report(actor=office, report=report, accept=True, note="")
        elif outcome == "returned":
            report = decide_report(actor=office, report=report, accept=False, note=LANI_RETURN_NOTE)
        if outcome in ("accepted", "returned"):
            decided.append(report)
    # The office has read what it decided; staff and heads have read their acceptances, while a
    # head's notice of a returned report stays new.
    urls = [office_url(r) for r in decided]
    urls += [staff_url(r) for r in decided if r.status == Report.Status.ACCEPTED]
    Notification.objects.filter(url__in=urls).update(read_at=timezone.now())


def give_report_samples() -> None:
    if not storage.is_configured():
        return
    program = Program.objects.filter(slug="tcu-ceaa", is_active=True).first()
    staff = _user("staff@scholarsync.test")
    head = _user("head@scholarsync.test")
    office = _user("office@scholarsync.test")
    if program is None or staff is None or head is None or office is None:
        return
    try:
        with transaction.atomic():
            # Each sample set skips itself once it exists, so a demo loaded before rev 33 gains
            # the report waiting for the head on the next run.
            if not Report.objects.filter(program=program).exclude(title=FOR_HEAD_TITLE).exists():
                _samples(program, staff, head, office)
            if not Report.objects.filter(program=program, title=FOR_HEAD_TITLE).exists():
                _for_head(program, staff, head)
            _more_samples(office)
    except (ValidationError, storage.StorageUnavailable) as error:
        # Log only the error class: service sentences can hold names.
        logger.warning("Demo report samples skipped (%s).", type(error).__name__)
