from datetime import timedelta

import pytest
from django.http import Http404, QueryDict
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.review_selectors import (
    STATUS_FILTERS,
    QueueFilters,
    behalf_in_progress,
    filing_profiles,
    history,
    parse_queue_filters,
    queue,
    queue_position,
    staff_application,
    waiting_count,
)
from apps.applications.tests.factories import ApplicationFactory, DocumentFactory
from apps.core import audit
from apps.programs.models import Program
from apps.programs.tests.factories import ProgramFactory
from apps.students.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

S = Application.Status


def submitted(program: Program, status: str = S.SUBMITTED, **kwargs: object) -> Application:
    now = timezone.now()
    kwargs.setdefault("submitted_at", now)
    kwargs.setdefault("first_submitted_at", kwargs["submitted_at"])
    return ApplicationFactory.create(program=program, status=status, **kwargs)


def ids(rows: object) -> list[int]:
    return [row.pk for row in rows]  # type: ignore[attr-defined]


def test_queue_hides_unsubmitted_drafts_and_other_programs() -> None:
    tcu = ProgramFactory.create()
    ApplicationFactory.create(program=tcu, status=S.DRAFT)
    ApplicationFactory.create(program=tcu, status=S.WITHDRAWN, submitted_at=None)
    submitted(ProgramFactory.create())
    row = submitted(tcu)
    assert ids(queue(tcu, QueueFilters(status="all"))) == [row.pk]


def test_waiting_filter_is_the_default() -> None:
    program = ProgramFactory.create()
    a = submitted(program)
    b = submitted(program, S.UNDER_REVIEW)
    submitted(program, S.RETURNED)
    submitted(program, S.APPROVED)
    filters = parse_queue_filters(QueryDict(""))
    assert filters.status == "waiting"
    assert set(ids(queue(program, filters))) == {a.pk, b.pk}


def test_queue_search_matches_every_word_in_first_or_last_name() -> None:
    program = ProgramFactory.create()
    santos = submitted(
        program, profile=ProfileFactory.create(first_name="Maria", last_name="Santos")
    )
    submitted(program, profile=ProfileFactory.create(first_name="Maria", last_name="Reyes"))
    assert ids(queue(program, QueueFilters(q="maria santos"))) == [santos.pk]
    assert ids(queue(program, QueueFilters(q="SANTOS maria"))) == [santos.pk]


def test_queue_search_treats_percent_and_underscore_literally() -> None:
    program = ProgramFactory.create()
    plain = submitted(program, profile=ProfileFactory.create(last_name="Abcd"))
    odd = submitted(program, profile=ProfileFactory.create(last_name="A_c%d"))
    assert ids(queue(program, QueueFilters(q="%"))) == [odd.pk]
    assert ids(queue(program, QueueFilters(q="_"))) == [odd.pk]
    assert ids(queue(program, QueueFilters(q="a_c"))) == [odd.pk]
    assert plain.pk not in ids(queue(program, QueueFilters(q="a_c")))


def test_parse_queue_filters_falls_back_on_garbage() -> None:
    filters = parse_queue_filters(QueryDict("status=nope&sort=bogus&term=abc&q=%20x%20"))
    assert filters == QueueFilters(status="waiting", term_id=None, q="x", sort="submitted")
    assert parse_queue_filters(QueryDict("sort=-name&term=7&status=all")) == QueueFilters(
        status="all", term_id=7, q="", sort="-name"
    )
    assert parse_queue_filters(QueryDict("term=99999999999999")).term_id is None
    assert set(STATUS_FILTERS) >= {"waiting", "all", "submitted", "withdrawn"}
    assert "draft" not in STATUS_FILTERS


def test_default_sort_is_oldest_first_submission() -> None:
    program = ProgramFactory.create()
    now = timezone.now()
    newer = submitted(program, first_submitted_at=now - timedelta(days=1))
    # Resubmitted today, but first submitted long ago: keeps its place.
    older = submitted(program, first_submitted_at=now - timedelta(days=9), submitted_at=now)
    filters = QueueFilters(status="all")
    assert ids(queue(program, filters)) == [older.pk, newer.pk]
    assert ids(queue(program, QueueFilters(status="all", sort="-submitted"))) == [
        newer.pk,
        older.pk,
    ]


def test_queue_sorts_by_name() -> None:
    program = ProgramFactory.create()
    b = submitted(program, profile=ProfileFactory.create(first_name="Z", last_name="Bravo"))
    a = submitted(program, profile=ProfileFactory.create(first_name="Y", last_name="Alpha"))
    assert ids(queue(program, QueueFilters(sort="name"))) == [a.pk, b.pk]
    assert ids(queue(program, QueueFilters(sort="-name"))) == [b.pk, a.pk]


def test_staff_application_404_for_other_program_and_drafts() -> None:
    program = ProgramFactory.create()
    mine = submitted(program)
    assert staff_application(program, mine.pk).pk == mine.pk
    with pytest.raises(Http404):
        staff_application(ProgramFactory.create(), mine.pk)
    draft = ApplicationFactory.create(program=program, status=S.DRAFT)
    with pytest.raises(Http404):
        staff_application(program, draft.pk)


def test_queue_position_previous_and_next() -> None:
    program = ProgramFactory.create()
    now = timezone.now()
    first = submitted(program, first_submitted_at=now - timedelta(days=3))
    middle = submitted(program, S.UNDER_REVIEW, first_submitted_at=now - timedelta(days=2))
    last = submitted(program, first_submitted_at=now - timedelta(days=1))
    position = queue_position(program, middle)
    assert (position.position, position.total, position.previous_id, position.next_id) == (
        2,
        3,
        first.pk,
        last.pk,
    )
    returned = submitted(program, S.RETURNED)
    outside = queue_position(program, returned)
    assert outside.position is None
    assert outside.total == 3
    assert outside.previous_id is None
    assert outside.next_id is None


def test_history_labels_actor_and_order() -> None:
    program = ProgramFactory.create()
    application = submitted(program)
    staff = UserFactory.create(full_name="Staff Person", role="staff")
    student = application.profile.user
    document = DocumentFactory.create(application=application)
    other = DocumentFactory.create()  # another application's document
    audit.record(actor=student, action="application.submitted", target=application)
    audit.record(actor=staff, action="application.review_started", target=application)
    audit.record(actor=staff, action="document.approved", target=document)
    audit.record(actor=staff, action="document.approved", target=other)
    audit.record(actor=None, action="application.mystery", target=application)
    audit.record(actor=None, action="application.withdrawn", target=application)
    entries = history(application)
    assert [(e.what, e.who) for e in entries] == [
        ("Submitted", "Student"),
        ("Review started", "Staff Person"),
        (f"{document.requirement.label} approved", "Staff Person"),
        ("Withdrawn", "System"),
    ]
    assert entries == sorted(entries, key=lambda e: e.at)


def test_history_labels_on_behalf_events() -> None:
    program = ProgramFactory.create()
    application = submitted(program, on_behalf=True)
    staff = UserFactory.create(full_name="Staff Person", role="staff")
    audit.record(actor=staff, action="application.started_on_behalf", target=application)
    audit.record(actor=staff, action="application.academics_set", target=application)
    audit.record(actor=staff, action="application.submitted", target=application)
    assert [(e.what, e.who) for e in history(application)] == [
        ("Application started by staff", "Staff Person"),
        ("School and grades entered", "Staff Person"),
        ("Submitted", "Staff Person"),
    ]


def test_waiting_count_counts_submitted_only() -> None:
    program = ProgramFactory.create()
    submitted(program)
    submitted(program)
    submitted(program, S.UNDER_REVIEW)
    submitted(program, S.APPROVED)
    submitted(ProgramFactory.create())
    ApplicationFactory.create(program=program, status=S.DRAFT)
    assert waiting_count(program) == 2


def test_parse_queue_filters_strips_nul_bytes_and_queue_still_runs() -> None:
    filters = parse_queue_filters(QueryDict("q=%00ab%00"))
    assert filters.q == "ab"
    program = ProgramFactory.create()
    assert list(queue(program, filters)) == []
    assert list(queue(program, parse_queue_filters(QueryDict("q=%00")))) == []


def test_queue_term_filter() -> None:
    program = ProgramFactory.create()
    a = submitted(program)
    submitted(program)
    assert ids(queue(program, QueueFilters(term_id=a.term_id))) == [a.pk]


def test_descending_submitted_sort_puts_null_first_submission_last() -> None:
    program = ProgramFactory.create()
    now = timezone.now()
    dated = submitted(program, first_submitted_at=now)
    undated = submitted(program, first_submitted_at=None)
    for sort in ("submitted", "-submitted"):
        assert ids(queue(program, QueueFilters(sort=sort)))[-1] == undated.pk
    assert dated.pk in ids(queue(program, QueueFilters(sort="-submitted")))


def test_filing_profiles_scoped_and_searched() -> None:
    program = ProgramFactory.create()
    ana = ProfileFactory.create(created_for=program, first_name="Ana Liza", last_name="Cruz")
    ben = ProfileFactory.create(created_for=program, first_name="Ben", last_name="Abad")
    ProfileFactory.create(created_for=ProgramFactory.create(), first_name="Ana", last_name="Cruz")
    ProfileFactory.create(first_name="Ana", last_name="Cruz")
    assert ids(filing_profiles(program, "")) == [ben.pk, ana.pk]
    assert ids(filing_profiles(program, "ana cruz")) == [ana.pk]
    assert ids(filing_profiles(program, "zzz")) == []
    assert ids(filing_profiles(program, "%")) == []


def test_behalf_in_progress_lists_draft_and_returned_only() -> None:
    program = ProgramFactory.create()
    draft = ApplicationFactory.create(program=program, on_behalf=True)
    returned = ApplicationFactory.create(program=program, on_behalf=True, status=S.RETURNED)
    ApplicationFactory.create(program=program, on_behalf=True, status=S.WITHDRAWN)
    ApplicationFactory.create(program=program)  # a student's own draft
    ApplicationFactory.create(on_behalf=True)  # another program
    assert set(ids(behalf_in_progress(program))) == {draft.pk, returned.pk}
    assert ids(behalf_in_progress(program))[0] == returned.pk  # newest update first
