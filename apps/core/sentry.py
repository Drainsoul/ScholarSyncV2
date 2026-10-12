from typing import Any
from urllib.parse import urlsplit, urlunsplit

from apps.core.redaction import redact

SAFE_HEADERS = {"User-Agent", "Referer", "Content-Type", "Accept", "Host"}


def _strip_frame_vars(container: dict[str, Any] | None) -> None:
    for item in (container or {}).get("values") or []:
        for frame in (item.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)


def _path_only(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Strip everything that can carry student PII before an event leaves the app.

    Drops request bodies, cookies, query strings and auth headers; keeps only the Referer's path;
    keeps user identity's id only; drops stack-frame locals (exceptions and threads), log params,
    `extra` and breadcrumb data; and redacts exception values and messages. Exception types and
    stack positions stay, so errors remain debuggable.
    """
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            kept = {k: v for k, v in headers.items() if k in SAFE_HEADERS}
            if "Referer" in kept:
                kept["Referer"] = _path_only(str(kept["Referer"]))
            request["headers"] = kept
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    _strip_frame_vars(event.get("exception"))
    _strip_frame_vars(event.get("threads"))
    for exception in (event.get("exception") or {}).get("values") or []:
        if isinstance(exception.get("value"), str):
            exception["value"] = redact(exception["value"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        logentry.pop("params", None)
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = redact(logentry[key])
    if isinstance(event.get("message"), str):
        event["message"] = redact(event["message"])
    event.pop("extra", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        crumb.pop("data", None)
        if isinstance(crumb.get("message"), str):
            crumb["message"] = redact(crumb["message"])
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
                    "terms": ["user-agent", "content-type", "accept", "host"],
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
