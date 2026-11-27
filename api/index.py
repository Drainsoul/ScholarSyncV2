"""The Vercel function entry: the whole Django app as one WSGI function.

Branch `demo` only (docs/design/2026-11-28-hosted-demo-design.md section 5.3); vercel.json routes
every path here.
"""

from config.wsgi import application as app

__all__ = ["app"]
