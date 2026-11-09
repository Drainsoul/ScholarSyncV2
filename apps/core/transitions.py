from typing import Any

from django.core.exceptions import ValidationError


class InvalidTransition(ValidationError):
    """Raised when a status change isn't in the model's TRANSITIONS table."""


def _label(obj: Any, value: str) -> str:
    status_enum = getattr(type(obj), "Status", None)
    if status_enum is not None:
        try:
            return str(status_enum(value).label)
        except ValueError:
            pass
    return str(value)


def assert_transition(obj: Any, new_status: str) -> None:
    allowed = type(obj).TRANSITIONS.get(obj.status, frozenset())
    if new_status not in allowed:
        raise InvalidTransition(
            f"Can't change from {_label(obj, obj.status)} to {_label(obj, new_status)}."
        )
