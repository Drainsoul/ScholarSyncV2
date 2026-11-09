from dataclasses import dataclass
from typing import ClassVar

import pytest
from django.db import models

from apps.core.transitions import InvalidTransition, assert_transition


@dataclass
class Thing:
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        WITHDRAWN = "withdrawn", "Withdrawn"

    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        "draft": frozenset({"submitted", "withdrawn"}),
        "submitted": frozenset({"withdrawn"}),
    }
    status: str


def test_allowed_transition_passes() -> None:
    assert_transition(Thing(status="draft"), "submitted")


def test_disallowed_transition_raises_with_labels() -> None:
    with pytest.raises(InvalidTransition) as exc:
        assert_transition(Thing(status="withdrawn"), "submitted")
    assert exc.value.messages == ["Can't change from Withdrawn to Submitted."]


def test_unknown_current_status_raises() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(Thing(status="mystery"), "submitted")
