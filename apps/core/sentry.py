from typing import Any

SAFE_HEADERS = {"User-Agent", "Referer", "Content-Type", "Accept", "Host"}


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Strip everything that can carry student PII before an event leaves the app.

    Drops request bodies, cookies, query strings and auth headers; user identity except the id;
    stack-frame local variables; and breadcrumb data (e.g. SQL parameters). Messages, exception
    types and stack positions stay, so errors remain debuggable.
    """
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
    for exception in (event.get("exception") or {}).get("values") or []:
        for frame in (exception.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        crumb.pop("data", None)
    return event


def init_sentry(*, dsn: str, environment: str, release: str | None) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[DjangoIntegration()],
        # Explicit per-category opt-outs (replaces the deprecated send_default_pii=False).
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {
                "request": {
                    "mode": "allowlist",
                    "terms": ["user-agent", "referer", "content-type", "accept", "host"],
                }
            },
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "database_query_data": False,
            "stack_frame_variables": False,
            "gen_ai": {"inputs": False, "outputs": False},
            "graphql": {"document": False, "variables": False},
        },
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,  # type: ignore[arg-type]
        traces_sample_rate=0.0,
    )
