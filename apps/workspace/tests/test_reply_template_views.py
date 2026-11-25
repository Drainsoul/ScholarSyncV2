"""The office's reply template screens (spec §12 rev 35)."""

from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.models import ReplyTemplate
from apps.workspace.tests.factories import ReplyTemplateFactory

pytestmark = pytest.mark.django_db

LIST = "/office/support/templates/"


@pytest.fixture
def office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def test_list_shows_columns_for_active_and_inactive(client: Any, office: User) -> None:
    lani = ProgramFactory.create(name="LANI")
    ReplyTemplateFactory.create(title="Late allowance", topic="allowance", program=lani)
    ReplyTemplateFactory.create(title="Old one", is_active=False)
    html = client.get(LIST).content.decode()
    assert "Late allowance" in html and "An allowance" in html and "LANI" in html
    assert "Old one" in html and "Any topic" in html and "Every program" in html
    assert ">On<" in html and ">Off<" in html


def test_add_and_edit_save_and_audit(client: Any, office: User) -> None:
    response = client.post(
        reverse("support:template-new"),
        {
            "title": "Review time",
            "topic": "application",
            "program": "",
            "subject": "",
            "body": "Hi",
        },
        follow=True,
    )
    assert "Template added." in response.content.decode()
    template = ReplyTemplate.objects.get()
    assert (template.topic, template.program, template.created_by) == ("application", None, office)
    response = client.post(
        reverse("support:template-edit", args=[template.pk]),
        {"title": "Review time", "topic": "", "program": "", "subject": "Re", "body": "Hello"},
        follow=True,
    )
    assert "Template saved." in response.content.decode()
    template.refresh_from_db()
    assert (template.topic, template.subject, template.body) == ("", "Re", "Hello")
    assert AuditEvent.objects.filter(action__startswith="support_template.").count() == 2


def test_duplicate_title_on_add_is_a_form_error(client: Any, office: User) -> None:
    ReplyTemplateFactory.create(title="Review time")
    response = client.post(
        reverse("support:template-new"),
        {"title": "Review time", "topic": "", "program": "", "subject": "", "body": "Hi"},
    )
    assert response.status_code == 200
    assert "An active template already has this title." in response.content.decode()


@pytest.mark.parametrize("subject", ["About\nBcc: x@example.com", "About\r\nyour request"])
def test_subject_with_a_line_break_is_a_form_error(client: Any, office: User, subject: str) -> None:
    data = {"title": "Review time", "topic": "", "program": "", "subject": subject, "body": "Hi"}
    response = client.post(reverse("support:template-new"), data)
    assert response.status_code == 200
    assert "Enter the subject on one line." in response.content.decode()
    template = ReplyTemplateFactory.create(title="Other")
    response = client.post(reverse("support:template-edit", args=[template.pk]), data)
    assert "Enter the subject on one line." in response.content.decode()
    template.refresh_from_db()
    assert template.subject == ""
    assert not ReplyTemplate.objects.filter(title="Review time").exists()


def test_turn_off_and_on_with_toasts(client: Any, office: User) -> None:
    template = ReplyTemplateFactory.create()
    url = reverse("support:template-active", args=[template.pk])
    assert "Template turned off." in client.post(url, {"active": "0"}, follow=True).content.decode()
    template.refresh_from_db()
    assert not template.is_active
    assert "Template turned on." in client.post(url, {"active": "1"}, follow=True).content.decode()


def test_turn_on_with_clashing_title_shows_error(client: Any, office: User) -> None:
    old = ReplyTemplateFactory.create(title="Same", is_active=False)
    ReplyTemplateFactory.create(title="Same")
    response = client.post(
        reverse("support:template-active", args=[old.pk]), {"active": "1"}, follow=True
    )
    assert "An active template already has this title." in response.content.decode()
    old.refresh_from_db()
    assert not old.is_active


def test_only_the_office_sees_the_link(client: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(office)
    assert f'href="{LIST}"' in client.get("/office/support/").content.decode()
    program = ProgramFactory.create(slug="lani")
    staff = UserFactory.create(role=User.Role.STAFF)
    MembershipFactory.create(user=staff, program=program, level="head")
    client.force_login(staff)
    assert LIST not in client.get("/staff/lani/support/").content.decode()
    assert client.get(LIST).status_code == 403


def test_editing_keeps_a_closed_programs_template_on_that_program(
    client: Any, office: User
) -> None:
    closed = ProgramFactory.create(name="Old grant", is_active=False)
    template = ReplyTemplateFactory.create(program=closed)
    html = client.get(reverse("support:template-edit", args=[template.pk])).content.decode()
    assert f'<option value="{closed.pk}" selected>Old grant</option>' in html
    client.post(
        reverse("support:template-edit", args=[template.pk]),
        {
            "title": template.title,
            "topic": "",
            "program": str(closed.pk),
            "subject": "",
            "body": "Hi",
        },
    )
    template.refresh_from_db()
    assert template.program == closed
