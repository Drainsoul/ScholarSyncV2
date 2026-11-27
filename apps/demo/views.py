"""Vercel Cron's nightly reset (branch `demo`, docs/design/2026-11-28-hosted-demo-design.md 5.4).

Vercel signs every cron call with `Authorization: Bearer <CRON_SECRET>`. Anything else gets the
same 404 as an unknown page, so the route can't be probed.
"""

import hmac

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from apps.demo import reset


def _signed_by_cron(request: HttpRequest) -> bool:
    secret = getattr(settings, "CRON_SECRET", "")
    if not secret or not getattr(settings, "PUBLIC_DEMO", False):
        return False
    header = request.headers.get("Authorization", "")
    return hmac.compare_digest(header.encode(), f"Bearer {secret}".encode())


# The secret is checked before anything else, so every unsigned request gets the 404 an unknown page
# gets, whatever its method; CSRF would answer an unsigned POST with 403 and show the route exists.
# Exempting it is safe: the bearer header is the only credential, and nothing but GET does anything.
@csrf_exempt
@never_cache
def reset_view(request: HttpRequest) -> HttpResponse:
    if not _signed_by_cron(request):
        raise Http404("Not found.")
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    result = reset.reset()
    return JsonResponse(
        {
            "files_deleted": result.files_deleted,
            "accounts_created": result.accounts_created,
            "seconds": result.seconds,
        }
    )
