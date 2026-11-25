"""Office reply templates: the picker, placeholders and changes (spec §4.8 rev 35)."""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.tests.factories import ProgramFactory
from apps.workspace import reply_templates
from apps.workspace.tests.factories import ReplyTemplateFactory, SupportRequestFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN)


def test_picker_filters_and_orders() -> None:
    lani, other = ProgramFactory.create(name="LANI"), ProgramFactory.create()
    row = SupportRequestFactory.create(topic="allowance", program=lani)
    any_b = ReplyTemplateFactory.create(title="B any")
    any_a = ReplyTemplateFactory.create(title="A any")
    topical = ReplyTemplateFactory.create(title="Z allowance", topic="allowance")
    for_lani = ReplyTemplateFactory.create(title="Y lani", program=lani)
    ReplyTemplateFactory.create(title="Wrong topic", topic="account")
    ReplyTemplateFactory.create(title="Other program", program=other)
    ReplyTemplateFactory.create(title="Off", is_active=False)
    assert reply_templates.picker(row) == [topical, any_a, any_b, for_lani]


def test_fill_placeholders() -> None:
    lani = ProgramFactory.create(name="LANI")
    template = ReplyTemplateFactory.create(
        subject="About {program}", body="Hi {first_name}, about {program} {other}"
    )
    row = SupportRequestFactory.create(
        sender=UserFactory.create(full_name="Ana Reyes"), program=lani, topic="allowance"
    )
    assert reply_templates.fill(template, row) == ("About LANI", "Hi Ana, about LANI {other}")
    loose = SupportRequestFactory.create(sender=UserFactory.create(full_name=""), topic="allowance")
    blank = ReplyTemplateFactory.create(body="Hi {first_name}, from {program}")
    assert reply_templates.fill(blank, loose) == (
        "Re: your message about an allowance",
        "Hi there, from the scholarship office",
    )


@pytest.mark.parametrize(
    ("topic", "about"),
    [
        ("account", "your account"),
        ("profile", "your profile"),
        ("application", "an application"),
        ("allowance", "an allowance"),
        ("other", "something else"),
    ],
)
def test_default_subject_per_topic(topic: str, about: str) -> None:
    row = SupportRequestFactory.create(topic=topic)
    assert reply_templates.default_subject(row) == f"Re: your message about {about}"


def test_reactivate_with_clashing_title_refused(office: User) -> None:
    old = ReplyTemplateFactory.create(title="Late allowance", is_active=False)
    ReplyTemplateFactory.create(title="Late allowance")
    with pytest.raises(ValidationError) as caught:
        reply_templates.set_active(actor=office, template=old, active=True)
    assert caught.value.messages == ["An active template already has this title."]
    old.refresh_from_db()
    assert not old.is_active


def test_template_audit_events(office: User) -> None:
    template = reply_templates.create_template(
        actor=office, title="Late", topic="", program=None, subject="", body="Secret body"
    )
    reply_templates.update_template(actor=office, template=template, title="Late 2", body="x")
    reply_templates.set_active(actor=office, template=template, active=False)
    reply_templates.set_active(actor=office, template=template, active=True)
    events = list(AuditEvent.objects.order_by("pk").values_list("action", "data"))
    assert [a for a, _ in events] == [
        "support_template.created",
        "support_template.updated",
        "support_template.deactivated",
        "support_template.activated",
    ]
    assert events[1][1] == {"fields": ["title", "body"]}
    assert "Secret" not in str(events)
    template.refresh_from_db()
    assert template.updated_by == office


@pytest.fixture
def raced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Another save took the title after the check passed: only the constraint can see it."""
    monkeypatch.setattr(reply_templates, "_title_taken", lambda *args, **kwargs: False)


def test_create_race_on_title_is_a_form_error(office: User, raced: None) -> None:
    ReplyTemplateFactory.create(title="Late allowance")
    with pytest.raises(ValidationError) as caught:
        reply_templates.create_template(
            actor=office, title="Late allowance", topic="", program=None, subject="", body="x"
        )
    assert caught.value.messages == [reply_templates.TITLE_CLASH]
    assert not AuditEvent.objects.filter(action="support_template.created").exists()


def test_update_race_on_title_is_a_form_error(office: User, raced: None) -> None:
    ReplyTemplateFactory.create(title="Late allowance")
    template = ReplyTemplateFactory.create(title="Other")
    with pytest.raises(ValidationError) as caught:
        reply_templates.update_template(actor=office, template=template, title="Late allowance")
    assert caught.value.messages == [reply_templates.TITLE_CLASH]
    template.refresh_from_db()
    assert template.title == "Other"


def test_reactivate_race_on_title_is_a_form_error(office: User, raced: None) -> None:
    old = ReplyTemplateFactory.create(title="Late allowance", is_active=False)
    ReplyTemplateFactory.create(title="Late allowance")
    with pytest.raises(ValidationError) as caught:
        reply_templates.set_active(actor=office, template=old, active=True)
    assert caught.value.messages == [reply_templates.TITLE_CLASH]
    old.refresh_from_db()
    assert not old.is_active
