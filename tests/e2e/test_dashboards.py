import re
from datetime import timedelta
from typing import Literal
from urllib.parse import urljoin

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.money.tests.factories import ScheduleFactory
from apps.programs.tests.factories import AcademicTermFactory, MembershipFactory, ProgramFactory
from apps.students.tests.factories import ProfileFactory
from apps.workspace.models import SupportRequest
from apps.workspace.services import notify
from apps.workspace.tests.factories import TaskFactory
from tests.e2e.conftest import axe_violations
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)


def test_student_dashboard_bell_and_center(page: Page, live_server, vite_build, console_errors):
    profile = ProfileFactory.create()
    assert profile.user is not None
    application = ApplicationFactory.create(profile=profile)
    notify(
        user=profile.user,
        kind="application_received",
        title=f"We received your {application.program.name} application",
        url=f"/me/applications/{application.pk}/",
    )
    log_in(page, live_server.url, profile.user.email)
    bell = page.get_by_role("link", name="Notifications, 1 unread")
    expect(bell).to_be_visible()
    bell.click()
    expect(page.get_by_role("heading", name="Notifications", level=1)).to_be_visible()
    page.get_by_role(
        "link", name=f"We received your {application.program.name} application"
    ).click()
    expect(page).to_have_url(f"{live_server.url}/me/applications/{application.pk}/")
    expect(page.get_by_role("link", name="Notifications", exact=True)).to_be_visible()
    assert console_errors == []


def test_staff_task_round_trip(page: Page, live_server, vite_build, console_errors):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    log_in(page, live_server.url, staff.email, "/staff/tcu-ceaa/tasks/")
    page.get_by_role("link", name="Add task").click()
    dialog = page.get_by_role("dialog", name="Add a task")
    dialog.get_by_role("textbox", name="Task (required)").fill("Call the registrar")
    yesterday = timezone.localdate() - timedelta(days=1)
    dialog.get_by_label("Due date").fill(yesterday.isoformat())
    dialog.get_by_role("button", name="Add task").click()
    expect(page.get_by_text("Task added.")).to_be_visible()
    page.goto(f"{live_server.url}/staff/tcu-ceaa/")
    expect(page.get_by_text("1 of your tasks is overdue")).to_be_visible()
    page.goto(f"{live_server.url}/staff/tcu-ceaa/tasks/")
    page.get_by_role("button", name=re.compile(r"^Done\W+Call the registrar$")).click()
    expect(page.get_by_text("Task done.")).to_be_visible()
    expect(page.get_by_role("link", name="Call the registrar")).to_have_count(0)
    page.goto(f"{live_server.url}/staff/tcu-ceaa/")
    expect(page.get_by_text("1 of your tasks is overdue")).to_have_count(0)
    assert console_errors == []


def test_support_message_reaches_the_office(browser, live_server, vite_build):
    student = ProfileFactory.create().user
    assert student is not None
    office = _office()
    student_page = browser.new_page()
    log_in(student_page, live_server.url, student.email, "/me/support/")
    student_page.get_by_label("What is it about?").select_option(label="An allowance")
    student_page.get_by_role("textbox", name="Your message (required)").fill(
        "When is the next claim day?"
    )
    student_page.get_by_role("button", name="Send message").click()
    expect(
        student_page.get_by_text("Message sent. You'll find the answer under Replies.")
    ).to_be_visible()

    office_page = browser.new_page()
    log_in(office_page, live_server.url, office.email, "/office/")
    expect(office_page.get_by_text("1 support request is waiting")).to_be_visible()
    office_page.get_by_role("link", name="Support", exact=False).first.click()
    expect(office_page.get_by_text("When is the next claim day?")).to_be_visible()
    office_page.get_by_role("button", name="Mark as answered").click()
    expect(office_page.get_by_text("Marked as answered.")).to_be_visible()
    assert SupportRequest.objects.get().status == SupportRequest.Status.ANSWERED

    student_page.reload()
    expect(student_page.get_by_text("Answered", exact=True)).to_be_visible()


def test_office_overview_has_no_dead_links(page: Page, live_server, vite_build):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    sent = timezone.now() - timedelta(days=9)
    ApplicationFactory.create(
        program=program,
        status=Application.Status.SUBMITTED,
        submitted_at=sent,
        first_submitted_at=sent,
    )
    log_in(page, live_server.url, _office().email, "/office/")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Good")
    hrefs = page.eval_on_selector_all(
        "#main a[href]", "links => links.map(link => link.getAttribute('href'))"
    )
    assert hrefs
    for href in hrefs:
        assert href != "#"
        response = page.request.get(urljoin(page.url, href))  # "?month=…" is relative
        assert response.status < 400, href


@pytest.mark.parametrize("who", ["student", "staff", "office"])
def test_dashboards_have_landmarks_and_one_h1(page: Page, live_server, vite_build, who: str):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    if who == "student":
        user = ProfileFactory.create().user
        path = "/me/"
    elif who == "staff":
        user = MembershipFactory.create(program=program, user__verified=True).user
        path = "/staff/tcu-ceaa/"
    else:
        user = _office()
        path = "/office/"
    assert user is not None
    log_in(page, live_server.url, user.email, path)
    expect(page.locator("h1")).to_have_count(1)
    expect(page.locator("main#main")).to_have_count(1)
    expect(page.get_by_role("navigation", name="Main")).to_have_count(1)
    width = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert width is True


def test_staff_calendar_on_a_phone(page: Page, live_server, vite_build, axe_source, console_errors):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    today = timezone.localdate()
    TaskFactory.create(owner=staff, program=program, title="Call the registrar", due_on=today)
    ScheduleFactory.create(program=program, distribution_date=today, is_published=True)
    page.set_viewport_size({"width": 375, "height": 812})
    log_in(page, live_server.url, staff.email, "/staff/tcu-ceaa/")
    calendar = page.locator("#staff-calendar")
    day = calendar.get_by_role("link", name=f"{today.day} {today:%B %Y}, 2 items")
    for link in (
        calendar.get_by_role("link", name="Call the registrar"),
        calendar.get_by_role("link", name="Allowance release"),
        day,
    ):
        box = link.bounding_box()
        assert box is not None and box["width"] >= 24 and box["height"] >= 24, box
    assert axe_violations(page, axe_source) == []
    # The task chip keeps its own target above the cell's day link.
    calendar.get_by_role("link", name="Call the registrar").click()
    expect(page).to_have_url(re.compile(r"/staff/tcu-ceaa/tasks/\d+/$"))
    assert console_errors == []


def _day_name(day) -> str:
    return f"{day:%A}, {day.day} {day:%B %Y}"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_staff_day_dialog_and_add_task_for_this_day(
    page: Page,
    live_server,
    vite_build,
    axe_source,
    console_errors,
    scheme: Literal["light", "dark"],
):
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    staff = MembershipFactory.create(program=program, user__verified=True).user
    today = timezone.localdate()
    program.applications_close_on = today
    program.save(update_fields=["applications_close_on"])
    title = "Call the TCU registrar about the missing grade reports of the second-year scholars"
    TaskFactory.create(owner=staff, program=program, title=title, due_on=today)
    page.emulate_media(color_scheme=scheme)
    log_in(page, live_server.url, staff.email, "/staff/tcu-ceaa/")
    cell = page.locator("#staff-calendar td[aria-current=date]")
    box = cell.bounding_box()
    assert box is not None
    # Anywhere in the cell but the task link: here its right edge, beside the chips.
    cell.click(position={"x": box["width"] - 2, "y": box["height"] / 2})
    dialog = page.get_by_role("dialog", name=_day_name(today))
    expect(dialog).to_be_visible()
    expect(dialog.get_by_text(title, exact=True)).to_be_visible()  # in full, no ellipsis
    expect(dialog.get_by_text("Your task due")).to_be_visible()
    expect(dialog.get_by_role("listitem").filter(has_text="Applications close")).to_have_text(
        "Applications close Last day"
    )
    expect(dialog.get_by_role("link", name=f"Open task: {title}")).to_be_visible()
    assert axe_violations(page, axe_source) == []
    dialog.get_by_role("link", name="Add task for this day").click()
    form = page.get_by_role("dialog", name="Add a task")
    expect(form.get_by_label("Due date")).to_have_value(today.isoformat())
    expect(form.get_by_role("textbox", name="Task (required)")).to_be_focused()
    form.get_by_role("textbox", name="Task (required)").fill("Print the claim list")
    form.get_by_role("button", name="Add task").click()
    expect(page.get_by_text("Task added.")).to_be_visible()
    expect(
        page.locator("#staff-calendar").get_by_role(
            "link", name=f"{today.day} {today:%B %Y}, 3 items"
        )
    ).to_be_visible()
    assert console_errors == []


def test_student_day_dialog_on_a_phone(
    page: Page, live_server, vite_build, axe_source, console_errors
):
    term = AcademicTermFactory.create(is_current=True)
    profile = ProfileFactory.create()
    assert profile.user is not None
    today = timezone.localdate()
    program = ProgramFactory.create(name="LANI", applications_close_on=today)
    ApplicationFactory.create(profile=profile, program=program, term=term)
    page.set_viewport_size({"width": 375, "height": 812})
    log_in(page, live_server.url, profile.user.email, "/me/")
    page.locator("#home-calendar td[aria-current=date]").click()
    dialog = page.get_by_role("dialog", name=_day_name(today))
    expect(dialog.get_by_text("LANI applications close")).to_be_visible()
    expect(dialog.get_by_text("Last day to submit")).to_be_visible()
    expect(dialog.get_by_role("link", name="Add task for this day")).to_have_count(0)
    assert axe_violations(page, axe_source) == []
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(page.locator("#home-calendar td[aria-current=date] a")).to_be_focused()
    assert console_errors == []


def test_office_empty_day_dialog(page: Page, live_server, vite_build, console_errors):
    log_in(page, live_server.url, _office().email, "/office/")
    today = timezone.localdate()
    page.locator("#office-calendar").get_by_role(
        "link", name=f"{today.day} {today:%B %Y}, no items"
    ).click()
    dialog = page.get_by_role("dialog", name=_day_name(today))
    expect(dialog.get_by_text("Nothing on this day.")).to_be_visible()
    dialog.get_by_role("link", name="Add task for this day").click()
    form = page.get_by_role("dialog", name="Add a task")
    expect(form.get_by_label("Due date")).to_have_value(today.isoformat())
    assert console_errors == []


def test_office_copies_a_support_email(page: Page, live_server, vite_build, console_errors):
    from apps.workspace.tests.factories import SupportRequestFactory

    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    request = SupportRequestFactory.create()
    log_in(page, live_server.url, _office().email, "/office/support/")
    page.get_by_role("button", name=f"Copy {request.sender.email}").click()
    tip = page.locator(".copy-tip")
    expect(tip).to_have_text("Copied")
    expect(page.locator("[aria-live='polite']").filter(has_text="Copied")).to_have_count(1)
    expect(page.locator(".toast")).to_have_count(0)  # a small action gets no toast
    assert page.evaluate("navigator.clipboard.readText()") == request.sender.email
    expect(tip).to_have_count(0)  # gone after a moment
    assert console_errors == []
