from typing import Any

SAFE_HEADERS = {"User-Agent", "Referer", "Content-Type", "Accept", "Host"}


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Drop request bodies, cookies, query strings, auth headers and user identity except the id."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k in SAFE_HEADERS}
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    return event


def init_sentry(*, dsn: str, environment: str, release: str | None) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
        before_send=scrub_event,  # type: ignore[arg-type]
        traces_sample_rate=0.0,
    )
