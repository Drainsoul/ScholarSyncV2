"""Staff-side reads for application review. Pure reads: nothing here writes."""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import F, OrderBy, Q, QuerySet
from django.http import Http404, QueryDict

from apps.applications.models import Application, Document
from apps.core.models import AuditEvent
from apps.programs.models import Program
from apps.students.models import StudentProfile

WAITING_STATUSES = frozenset({Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW})

STATUS_FILTERS: dict[str, tuple[str, frozenset[str] | None]] = {
    "waiting": ("Waiting", WAITING_STATUSES),
    **{
        status.value: (status.label, frozenset({status.value}))
        for status in Application.Status
        if status != Application.Status.DRAFT
    },
    "all": ("All", None),
}

SORTS: dict[str, tuple[str, ...]] = {
    "submitted": ("first_submitted_at", "pk"),
    "name": ("profile__last_name", "profile__first_name", "pk"),
}

DEFAULT_STATUS = "waiting"
KINDS = frozenset({Application.Kind.NEW, Application.Kind.RENEWAL})
DEFAULT_SORT = "submitted"
MAX_TERM_ID = 2**31 - 1


@dataclass(frozen=True)
class QueueFilters:
    status: str = DEFAULT_STATUS
    term_id: int | None = None
    q: str = ""
    sort: str = DEFAULT_SORT
    kind: str = ""  # "", "new" or "renewal"


@dataclass(frozen=True)
class QueuePosition:
    position: int | None
    total: int
    previous_id: int | None
    next_id: int | None


@dataclass(frozen=True)
class HistoryEntry:
    what: str
    at: datetime
    who: str


HISTORY_LABELS: dict[str, str] = {
    "application.started": "Application started",
    "application.started_on_behalf": "Application started by staff",
    "application.renewal_started": "Renewal started",
    "application.academics_set": "School and grades entered",
    "application.submitted": "Submitted",
    "application.resubmitted": "Resubmitted",
    "application.withdrawn": "Withdrawn",
    "application.review_started": "Review started",
    "application.returned": "Returned to the student",
    "application.approved": "Approved",
    "application.rejected": "Rejected",
    "document.uploaded": "uploaded",
    "document.approved": "approved",
    "document.declined": "declined",
}


def applications_for_program(program: Program) -> QuerySet[Application]:
    """The program's submitted applications, unordered. Services lock rows from this queryset."""
    return Application.objects.filter(program=program, submitted_at__isnull=False)


def parse_queue_filters(params: QueryDict) -> QueueFilters:
    status = params.get("status", "")
    if status not in STATUS_FILTERS:
        status = DEFAULT_STATUS
    raw_term = params.get("term", "").strip()
    term_id = int(raw_term) if raw_term.isascii() and raw_term.isdigit() else None
    if term_id is not None and term_id > MAX_TERM_ID:
        term_id = None
    sort = params.get("sort", "")
    if sort.removeprefix("-") not in SORTS:
        sort = DEFAULT_SORT
    kind = params.get("kind", "")
    if kind not in KINDS:
        kind = ""
    return QueueFilters(
        status=status,
        term_id=term_id,
        q=params.get("q", "").replace("\x00", "").strip(),
        sort=sort,
        kind=kind,
    )


def _order_fields(sort: str) -> list[OrderBy | str]:
    fields = SORTS[sort.removeprefix("-")]
    if sort.startswith("-"):
        # Nulls last in both directions, so asc and desc agree on rows with no first submission.
        return [F(field).desc(nulls_last=True) for field in fields]
    return list(fields)


def queue(program: Program, filters: QueueFilters) -> QuerySet[Application]:
    rows = applications_for_program(program).select_related(
        "profile", "term", "requested_tier", "school"
    )
    statuses = STATUS_FILTERS[filters.status][1]
    if statuses is not None:
        rows = rows.filter(status__in=statuses)
    if filters.term_id is not None:
        rows = rows.filter(term_id=filters.term_id)
    if filters.kind:
        rows = rows.filter(kind=filters.kind)
    # icontains escapes % and _ itself; every word must match the first or the last name.
    for word in filters.q.split():
        rows = rows.filter(
            Q(profile__first_name__icontains=word) | Q(profile__last_name__icontains=word)
        )
    return rows.order_by(*_order_fields(filters.sort))


def staff_application(program: Program, pk: int) -> Application:
    application = (
        applications_for_program(program)
        .select_related(
            "profile",
            "profile__user",
            "term",
            "requested_tier",
            "school",
            "program",
            "created_by",
            "award__started_term",
        )
        .filter(pk=pk)
        .first()
    )
    if application is None:
        raise Http404("No such application.")
    return application


def waiting_count(program: Program) -> int:
    return applications_for_program(program).filter(status=Application.Status.SUBMITTED).count()


def queue_position(program: Program, application: Application) -> QueuePosition:
    ids = list(
        applications_for_program(program)
        .filter(status__in=WAITING_STATUSES)
        .order_by("first_submitted_at", "pk")
        .values_list("pk", flat=True)
    )
    try:
        index = ids.index(application.pk)
    except ValueError:
        return QueuePosition(position=None, total=len(ids), previous_id=None, next_id=None)
    return QueuePosition(
        position=index + 1,
        total=len(ids),
        previous_id=ids[index - 1] if index > 0 else None,
        next_id=ids[index + 1] if index + 1 < len(ids) else None,
    )


def history(application: Application) -> list[HistoryEntry]:
    documents = {
        document.pk: document
        for document in Document.objects.filter(application=application).select_related(
            "requirement"
        )
    }
    events = (
        AuditEvent.objects.filter(
            Q(target_type="applications.application", target_id=str(application.pk))
            | Q(target_type="applications.document", target_id__in=[str(pk) for pk in documents]),
            action__in=HISTORY_LABELS,
        )
        .select_related("actor")
        .order_by("at", "id")
    )
    student_user_id = application.profile.user_id
    entries = []
    for event in events:
        what = HISTORY_LABELS[event.action]
        if application.on_behalf and event.action == "application.returned":
            what = "Returned for fixes"
        if event.target_type == "applications.document":
            document = documents.get(int(event.target_id))
            label = document.requirement.label if document is not None else "Document"
            what = f"{label} {what}"
        if event.actor is None:
            who = "System"
        elif event.actor_id == student_user_id:
            who = "Student"
        else:
            who = event.actor.full_name
        entries.append(HistoryEntry(what=what, at=event.at, who=who))
    return entries


def filing_profiles(program: Program, q: str) -> QuerySet[StudentProfile]:
    """The profiles this program's staff created. Every word of `q` must match a name."""
    rows = StudentProfile.objects.filter(created_for=program)
    for word in q.split():
        rows = rows.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word))
    return rows.order_by("last_name", "first_name", "pk")


def behalf_in_progress(program: Program) -> QuerySet[Application]:
    """Applications staff are still filling in or that came back for changes, newest first."""
    return (
        Application.objects.filter(
            program=program,
            on_behalf=True,
            status__in=(Application.Status.DRAFT, Application.Status.RETURNED),
        )
        .select_related("profile", "term")
        .order_by("-updated_at", "-pk")
    )


def _behalf_rows(program: Program) -> QuerySet[Application]:
    return Application.objects.filter(program=program, on_behalf=True)


def behalf_application(program: Program, pk: int) -> Application:
    application = (
        _behalf_rows(program)
        .select_related("profile", "term", "requested_tier", "school", "program", "created_by")
        .filter(pk=pk)
        .first()
    )
    if application is None:
        raise Http404("No such application.")
    return application
