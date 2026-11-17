"""The student's home page: returned applications, scholarships, applications, allowances and
the latest notifications, in a fixed number of queries."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.selectors import applications_for_student
from apps.applications.wording import APPLICATION_TONES
from apps.awards.models import Award
from apps.awards.selectors import scholarships_for_student
from apps.money.models import Disbursement
from apps.money.selectors import STUDENT_STATUS, amount_for, payouts_for_student
from apps.programs.selectors import current_term, renewal_rule_text
from apps.workspace.models import Notification
from apps.workspace.selectors import notifications_for

APPLICATIONS_SHOWN = 5
ALLOWANCES_SHOWN = 3
NOTICES_SHOWN = 3
CARD_STATUSES = frozenset({Award.Status.ACTIVE, Award.Status.SUSPENDED})
PAYOUT_TONES = {
    Disbursement.Status.PENDING: "neutral",
    Disbursement.Status.APPROVED: "info",
    Disbursement.Status.RELEASED: "success",
    Disbursement.Status.REJECTED: "danger",
}


@dataclass(frozen=True)
class AwardCard:
    program_name: str
    status_label: str
    tier_name: str
    amount: Decimal
    next_release: date | None
    renew_text: str


@dataclass(frozen=True)
class StudentDashboard:
    term_label: str
    returned: list[Application]
    awards: list[AwardCard]
    applications: list[dict[str, object]]
    allowances: list[dict[str, object]]
    notices: list[Notification]


def student_dashboard(user: User, *, today: date) -> StudentDashboard:
    term = current_term()
    payouts = payouts_for_student(user, today=today)
    cards = []
    for card in scholarships_for_student(user, today=today):
        award = card.award
        if award.status not in CARD_STATUSES:
            continue
        latest = card.terms[0] if card.terms else None
        tier = latest.tier if latest is not None and latest.tier is not None else award.tier
        amount = amount_for(latest)[0] if latest is not None else tier.base_amount
        found = payouts.get(award.pk)
        schedule = found.next_schedule if found is not None else None
        cards.append(
            AwardCard(
                program_name=award.program.name,
                status_label=award.get_status_display(),
                tier_name=tier.name,
                amount=amount,
                next_release=schedule.distribution_date if schedule is not None else None,
                renew_text=renewal_rule_text(award.program),
            )
        )

    applications = list(applications_for_student(user)[:APPLICATIONS_SHOWN])
    rows = []
    for application in applications:
        sent = (
            timezone.localtime(application.first_submitted_at)
            if application.first_submitted_at
            else None
        )
        rows.append(
            {
                "application": application,
                "submitted": f"{sent.day} {sent:%b %Y}" if sent else "Not sent yet",
                "tone": APPLICATION_TONES[application.status],
            }
        )
    returned = list(
        applications_for_student(user).filter(status=Application.Status.RETURNED, on_behalf=False)
    )

    every = [row for found in payouts.values() for row in found.rows]
    every.sort(
        key=lambda row: (
            row.scholar_term.term.sort_key,
            row.schedule.distribution_date,
            row.pk,
        ),
        reverse=True,
    )
    allowances: list[dict[str, object]] = [
        {
            "term": str(row.scholar_term.term),
            "amount": row.amount,
            "label": STUDENT_STATUS[Disbursement.Status(row.status)],
            "tone": PAYOUT_TONES[Disbursement.Status(row.status)],
        }
        for row in every[:ALLOWANCES_SHOWN]
    ]
    return StudentDashboard(
        term_label=str(term) if term is not None else "",
        returned=returned,
        awards=cards,
        applications=rows,
        allowances=allowances,
        notices=list(notifications_for(user)[:NOTICES_SHOWN]),
    )
