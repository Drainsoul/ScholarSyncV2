"""Database rules for support replies and reply templates (spec §4.8 rev 35)."""

from typing import Any

import pytest
from django.db import DataError, IntegrityError, transaction

from apps.workspace.tests.factories import ReplyTemplateFactory, SupportReplyFactory

pytestmark = pytest.mark.django_db


def _refused(**fields: Any) -> None:
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        SupportReplyFactory.create(**fields)


def _template_refused(**fields: Any) -> None:
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        ReplyTemplateFactory.create(**fields)


def test_reply_body_length_constraint() -> None:
    _refused(body="")
    _refused(body="x" * 4001)
    assert SupportReplyFactory.create(body="x" * 4000).pk


def test_email_reply_needs_a_subject() -> None:
    _refused(channel="email", subject="")
    _refused(channel="app", subject="x")
    _refused(channel="email", subject="x" * 151)
    assert SupportReplyFactory.create(channel="email", subject="Re: your account").pk


def test_template_title_unique_among_active() -> None:
    ReplyTemplateFactory.create(title="Late allowance")
    _template_refused(title="Late allowance")
    assert ReplyTemplateFactory.create(title="Late allowance", is_active=False).pk


def test_template_body_and_title_length_constraint() -> None:
    _template_refused(body="")
    _template_refused(body="x" * 4001)
    _template_refused(title="")
    _template_refused(title="x" * 81)
