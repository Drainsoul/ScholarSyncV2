"""Staff filing writes: applications filed on a student's behalf. Audit data holds ids only.

Lock order: the StudentProfile row, then the Application row, as the student and review services.
Every lookup is scoped to the program: another program's profile or application is a 404.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.applications.selectors import holds_scholarship, open_application, rejected_this_term
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.core.transitions import assert_transition
from apps.programs.models import Program
from apps.programs.selectors import application_term
from apps.students.models import StudentProfile

STAFF_HELD = "This student already holds this scholarship."
STAFF_REJECTED = (
    "This student's application wasn't approved for {term}. They can apply again next term."
)
STUDENT_OPEN = (
    "This student already has an application for {program} this term. "
    "They need to finish or withdraw it."
)
NO_TERM = "Applications aren't open: the scholarship office hasn't set up the current school term."
WITH_REVIEWERS = "This application is with the reviewers now."


def _lock_behalf(actor: User, program: Program, pk: int) -> tuple[StudentProfile, Application]:
    """The program's on-behalf application `pk` and its profile, locked profile first."""
    require_program_staff(actor, program)
    profile_id = (
        Application.objects.filter(pk=pk, program=program, on_behalf=True)
        .values_list("profile_id", flat=True)
        .first()
    )
    if profile_id is None:
        raise Http404("No such application.")
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    locked = (
        Application.objects.select_for_update(of=("self",))
        .select_related("program", "term")
        .filter(pk=pk, program=program, on_behalf=True)
        .first()
    )
    if locked is None or locked.profile_id != profile.pk:  # never trust the earlier read
        raise Http404("No such application.")
    return profile, locked


@transaction.atomic
def start_on_behalf(
    *,
    actor: User,
    program: Program,
    profile_id: int,
    request: HttpRequest | None = None,
) -> Application:
    active = Program.objects.filter(pk=program.pk, is_active=True).first()
    if active is None:
        raise Http404("No such program.")
    require_program_staff(actor, active)
    profile = (
        StudentProfile.objects.select_for_update().filter(pk=profile_id, created_for=active).first()
    )
    if profile is None:
        raise Http404("No such student.")
    term = application_term(timezone.localdate())
    if term is None:
        raise ValidationError(NO_TERM)
    if holds_scholarship(profile, active, term):
        raise ValidationError(STAFF_HELD)
    if rejected_this_term(profile, active, term):
        raise ValidationError(STAFF_REJECTED.format(term=term))
    existing = open_application(profile, active, term)
    if existing is not None:
        if existing.on_behalf:
            return existing
        raise ValidationError(STUDENT_OPEN.format(program=active.name))
    try:
        with transaction.atomic():
            application = Application.objects.create(
                profile=profile,
                program=active,
                term=term,
                kind=Application.Kind.NEW,
                status=Application.Status.DRAFT,
                on_behalf=True,
                created_by=actor,
            )
    except IntegrityError:
        # Another path committed an open application after we looked: the partial index caught it.
        existing = open_application(profile, active, term)
        if existing is None:
            raise
        if existing.on_behalf:
            return existing
        raise ValidationError(STUDENT_OPEN.format(program=active.name)) from None
    audit.record(
        actor=actor,
        action="application.started_on_behalf",
        target=application,
        program=active,
        request=request,
        data={},
    )
    return application


@transaction.atomic
def withdraw_on_behalf(
    *,
    actor: User,
    program: Program,
    pk: int,
    request: HttpRequest | None = None,
) -> Application:
    _, locked = _lock_behalf(actor, program, pk)
    # A submitted row can be withdrawn by its student; staff can't once the reviewers have it.
    if locked.status in (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW):
        raise ValidationError(WITH_REVIEWERS)
    assert_transition(locked, Application.Status.WITHDRAWN)
    locked.status = Application.Status.WITHDRAWN
    locked.save(update_fields=["status", "updated_at"])
    audit.record(
        actor=actor,
        action="application.withdrawn",
        target=locked,
        program=locked.program,
        request=request,
    )
    return locked
