"""Vercel Cron's nightly reset (branch `demo`, docs/design/2026-11-28-hosted-demo-design.md 5.4).

Vercel signs every cron call with `Authorization: Bearer <CRON_SECRET>`. Anything else gets the
same 404 as an unknown page, so the route can't be probed.
"""

import hmac

from django.conf import settings
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.demo import reset


def _signed_by_cron(request: HttpRequest) -> bool:
    secret = getattr(settings, "CRON_SECRET", "")
    if not secret or not getattr(settings, "PUBLIC_DEMO", False):
        return False
    header = request.headers.get("Authorization", "")
    return hmac.compare_digest(header.encode(), f"Bearer {secret}".encode())


@never_cache
@require_GET
def reset_view(request: HttpRequest) -> JsonResponse:
    if not _signed_by_cron(request):
        raise Http404("Not found.")
    result = reset.reset()
    return JsonResponse(
        {
            "files_deleted": result.files_deleted,
            "accounts_created": result.accounts_created,
            "seconds": result.seconds,
        }
    )
