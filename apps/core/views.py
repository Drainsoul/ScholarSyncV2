from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness plus a database round trip. Public on purpose; it reveals nothing."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    response = JsonResponse({"ok": True})
    response["Cache-Control"] = "no-store"
    return response
