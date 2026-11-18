"""A seeded world for whole-app scans: real ids for every detail page, and `rows` of each listed
thing, so the rendered-page scan and the query budgets see filled pages."""

from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.core.audit import record
from apps.money.models import Disbursement
from apps.money.tests.builders import payout
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    RequiredDocumentFactory,
    SchoolFactory,
)
from apps.reports.tests.factories import ReportFactory, ReportFileFactory
from apps.students.tests.factories import (
    EducationRecordFactory,
    FamilyMemberFactory,
    ProfileFactory,
)
from apps.workspace.tests.factories import NotificationFactory, SupportRequestFactory, TaskFactory

SLUG = "tcu-ceaa"


def build_world(personas: dict[str, User | None], rows: int = 1) -> dict[str, dict[str, Any]]:
    """Seed the TCU CEAA program around the permission-matrix personas and return URL kwargs that
    reach real rows (URL name → kwargs). Names not returned keep the matrix's unknown ids."""
    tcu = Program.objects.get(slug=SLUG)
    now = timezone.now()
    term = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    later = AcademicTermFactory.create(school_year_start=2026, term=2)
    tier = BenefitTierFactory.create(program=tcu, code="standard", effective_from=term)
    requirement = RequiredDocumentFactory.create(program=tcu)
    student, staff, office = personas["student"], personas["staff"], personas["office"]
    assert student is not None and staff is not None and office is not None
    profile = ProfileFactory.create(user=student)
    family = FamilyMemberFactory.create(profile=profile)
    education = EducationRecordFactory.create(profile=profile)

    applications = []
    awards = []
    for n in range(rows):
        applicant = profile if n == 0 else ProfileFactory.create()
        applications.append(
            ApplicationFactory.create(
                profile=applicant,
                program=tcu,
                term=term,
                status=Application.Status.UNDER_REVIEW,
                submitted_at=now,
                first_submitted_at=now,
            )
        )
        award = AwardFactory.create(
            source_application__program=tcu, source_application__term=term, tier=tier
        )
        ScholarTermFactory.create(award=award, term=term, tier=tier)
        awards.append(award)
        ReportFileFactory.create(report=ReportFactory.create(program=tcu, submitted_by=staff))
        TaskFactory.create(owner=staff, program=tcu)
        SchoolFactory.create()
        SupportRequestFactory.create(sender=student, program=tcu)
        for user in (student, staff, office):
            NotificationFactory.create(recipient=user, url="/")
        record(actor=staff, action="award.created", target=award, program=tcu)
    behalf_profile = ProfileFactory.create(user=None, created_for=tcu)
    behalf = ApplicationFactory.create(
        profile=behalf_profile, program=tcu, term=term, on_behalf=True, created_by=staff
    )
    schedule = ScheduleFactory.create(program=tcu, term=term)
    for _ in range(rows):
        payout(schedule, status=Disbursement.Status.PENDING)
    report = ReportFactory.create(program=tcu, submitted_by=staff)
    task = TaskFactory.create(owner=staff, program=tcu)
    school = SchoolFactory.create()
    staff_tcu = {"program": SLUG}
    return {
        "review:detail": {**staff_tcu, "pk": applications[0].pk},
        "review:behalf": {**staff_tcu, "pk": behalf.pk},
        "review:behalf-academics": {**staff_tcu, "pk": behalf.pk},
        "applications:detail": {"pk": applications[0].pk},
        "scholars:detail": {**staff_tcu, "pk": awards[0].pk},
        "scholars:edit": {**staff_tcu, "pk": awards[0].pk},
        "scholars:status": {**staff_tcu, "pk": awards[0].pk},
        "scholars:term-new": {**staff_tcu, "pk": awards[0].pk},
        "scholars:term-edit": {**staff_tcu, "pk": awards[0].pk, "term": term.pk},
        "money:schedule-edit": {**staff_tcu, "pk": schedule.pk},
        "money:schedule": {**staff_tcu, "schedule": schedule.pk},
        "workspace:task-edit": {**staff_tcu, "pk": task.pk},
        "workspace:students-invite": {**staff_tcu, "profile_id": behalf_profile.pk},
        "reports:detail": {**staff_tcu, "pk": report.pk},
        "office:report-detail": {"pk": report.pk},
        "office:program-edit": {"pk": tcu.pk},
        "office:staff-detail": {"pk": staff.pk},
        "office:school-edit": {"pk": school.pk},
        "office:terms-current": {"pk": later.pk},
        "settings:tier-change": {**staff_tcu, "code": tier.code},
        "settings:document-edit": {**staff_tcu, "pk": requirement.pk},
        "students:profile-family-edit": {"pk": family.pk},
        "students:profile-family-delete": {"pk": family.pk},
        "students:profile-education-edit": {"pk": education.pk},
        "students:profile-education-delete": {"pk": education.pk},
    }
