"""Answering a support request with a reply template (spec §12 rev 35)."""

import pytest
from playwright.sync_api import Dialog, Page, expect

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.workspace.tests.factories import ReplyTemplateFactory, SupportRequestFactory
from tests.e2e.flows import log_in

pytestmark = pytest.mark.e2e


def test_picking_a_template_fills_and_confirms(
    page: Page, live_server, vite_build, console_errors
) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    row = SupportRequestFactory.create(
        sender=UserFactory.create(full_name="Ana Reyes"), topic="allowance"
    )
    ReplyTemplateFactory.create(title="Late allowance", body="Hi {first_name}, it is coming.")
    ReplyTemplateFactory.create(title="Ask again", body="Hi {first_name}, please write again.")
    log_in(page, live_server.url, office.email, f"/office/support/{row.pk}/")

    reply = page.locator("#reply")
    expect(reply.get_by_role("button", name="Use template")).to_be_hidden()
    body = reply.get_by_label("Message")
    reply.get_by_label("Template").select_option(label="Late allowance")
    expect(body).to_have_value("Hi Ana, it is coming.")

    body.fill("draft")
    answers: list[str] = []

    def dismiss(dialog: Dialog) -> None:
        answers.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", dismiss)
    reply.get_by_label("Template").select_option(label="Ask again")
    expect(body).to_have_value("draft")
    assert answers == ["Replace what you've typed with this template?"]

    page.once("dialog", lambda dialog: dialog.accept())
    reply.get_by_label("Template").select_option(label="Late allowance")
    expect(body).to_have_value("Hi Ana, it is coming.")

    email = page.locator("#email")
    email.get_by_label("Template").select_option(label="Ask again")
    expect(email.get_by_label("Subject")).to_have_value("Re: your message about an allowance")
    expect(email.get_by_label("Message")).to_have_value("Hi Ana, please write again.")
    assert console_errors == []
