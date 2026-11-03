import hashlib
import hmac
import logging

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import Model
from django.http import HttpRequest

from apps.accounts.models import User
from apps.programs.models import Program

from .models import AuditEvent

logger = logging.getLogger(__name__)


def hash_ip(ip: str) -> str:
    """HMAC-SHA256 of the address keyed with SECRET_KEY, so the raw IP is never stored."""
    if not ip:
        return ""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def client_ip(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    try:
        return get_adapter(request).get_client_ip(request) or ""
    except (PermissionDenied, ImproperlyConfigured) as exc:
        logger.warning("Client IP unavailable: %s", type(exc).__name__)
        return ""


def record(
    *,
    actor: User | None,
    action: str,
    target: Model | None = None,
    program: Program | None = None,
    data: dict[str, object] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    """Write one audit event. `data` must never hold emails, names or passwords."""
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        program=program,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        data=data or {},
        ip_hash=hash_ip(client_ip(request)),
    )
