"""The Vercel function entry: the whole Django app as one WSGI function.

Branch `demo` only (docs/design/2026-11-28-hosted-demo-design.md section 5.3). vercel.json rewrites
every path to `/api/index?__path=<path>`. The runtime hands the app the rewrite's destination
(`/api/index`), not the address the visitor asked for, so `app` puts the visitor's path back and
drops the marker from the query string before Django sees the request.
"""

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import unquote

from config.wsgi import application

MARKER = "__path="


def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
    parts = environ.get("QUERY_STRING", "").split("&") if environ.get("QUERY_STRING") else []
    marked = [part for part in parts if part.startswith(MARKER)]
    if marked:
        # unquote, not unquote_plus: a "+" in a path is a plus sign, not a space.
        environ["PATH_INFO"] = "/" + unquote(marked[-1][len(MARKER) :]).lstrip("/")
        environ["QUERY_STRING"] = "&".join(p for p in parts if not p.startswith(MARKER))
    return application(environ, start_response)


__all__ = ["app", "application"]
