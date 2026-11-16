"""Starting a scholar's renewal. Submitting it goes through `services.submit_application`.

Lock order: the StudentProfile row, then the Award row (no application row is locked here).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.selectors import open_application
from apps.applications.services import RENEWAL_NOT_ACTIVE, _require_student
from apps.awards.models import Award
from apps.awards.selectors import RenewalStatus, renewal_for
from apps.core import audit
from apps.matching.eligibility import window_reason
from apps.programs.selectors import application_term
from apps.students.models import StudentProfile

RENEWAL_SUMMER = "Scholarships aren't renewed for the summer term."
ALREADY_RENEWED = "Your scholarship is already renewed for {term}."
RENEWAL_REJECTED = "Your renewal wasn't approved for {term}. Contact the scholarship office."
OTHER_OPEN = "You already have an application for {program} this term. Finish or withdraw it first."


def _open_renewal_or_refuse(award: Award, existing: Application) -> Application:
    if existing.kind == Application.Kind.RENEWAL and existing.award_id == award.pk:
        return existing
    raise ValidationError(OTHER_OPEN.format(program=award.program.name))


@transaction.atomic
def start_renewal(*, user: User, award_id: int, request: HttpRequest | None = None) -> Application:
    """The student's draft renewal of their own award for the current term."""
    _require_student(user)
    profile = StudentProfile.objects.select_for_update().filter(user=user).first()
    if profile is None:
        raise Http404("No such scholarship.")
    award = (
        Award.objects.select_for_update(of=("self",))
        .select_related("program", "tier")
        .filter(pk=award_id, profile=profile, program__is_active=True)
        .first()
    )
    if award is None:
        raise Http404("No such scholarship.")
    today = timezone.localdate()
    term = application_term(today)
    renewal = renewal_for(award, term)
    if renewal.status == RenewalStatus.NOT_ACTIVE:
        raise ValidationError(RENEWAL_NOT_ACTIVE)
    if renewal.status == RenewalStatus.NO_TERM:
        raise ValidationError(window_reason(award.program, today, None))
    assert term is not None
    if renewal.status == RenewalStatus.SUMMER:
        raise ValidationError(RENEWAL_SUMMER)
    if renewal.status == RenewalStatus.RENEWED:
        raise ValidationError(ALREADY_RENEWED.format(term=term))
    if renewal.status == RenewalStatus.REJECTED:
        raise ValidationError(RENEWAL_REJECTED.format(term=term))
    existing = open_application(profile, award.program, term)
    if existing is not None:
        return _open_renewal_or_refuse(award, existing)
    reason = window_reason(award.program, today, term)
    if reason:
        raise ValidationError(reason)
    try:
        with transaction.atomic():
            application = Application.objects.create(
                profile=profile,
                program=award.program,
                term=term,
                kind=Application.Kind.RENEWAL,
                award=award,
                status=Application.Status.DRAFT,
                created_by=user,
            )
    except IntegrityError:
        # Another path committed an open application after we looked: the partial index caught it.
        existing = open_application(profile, award.program, term)
        if existing is None:
            raise
        return _open_renewal_or_refuse(award, existing)
    audit.record(
        actor=user,
        action="application.renewal_started",
        target=application,
        program=award.program,
        request=request,
        data={"award": award.pk},
    )
    return application
