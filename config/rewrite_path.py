"""Give Django the visitor's path behind the hosted demo's rewrite (branch `demo` only).

The hosting config rewrites every path to `/api/index?__path=<path>`, and the host's Python
runtime hands the app that destination rather than the address the visitor asked for.
`restore_path` puts the visitor's path back and drops the marker from the query string.
config/wsgi.py applies it only in the public demo (hosted demo design, section 5.3).
"""

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import unquote

MARKER = "__path="

WsgiApp = Callable[[dict[str, Any], Callable[..., Any]], Iterable[bytes]]


def restore_path(inner: WsgiApp) -> WsgiApp:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        query = environ.get("QUERY_STRING", "")
        parts = query.split("&") if query else []
        marked = [part for part in parts if part.startswith(MARKER)]
        if marked:
            # unquote, not unquote_plus: a "+" in a path is a plus sign, not a space.
            environ["PATH_INFO"] = "/" + unquote(marked[-1][len(MARKER) :]).lstrip("/")
            environ["QUERY_STRING"] = "&".join(p for p in parts if not p.startswith(MARKER))
        return inner(environ, start_response)

    app.restores_path = True  # type: ignore[attr-defined]
    return app
