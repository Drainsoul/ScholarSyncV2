"""The Vercel function entry: the whole Django app as one WSGI function.

Branch `demo` only (docs/design/2026-11-28-hosted-demo-design.md section 5.3). vercel.json rewrites
every path here; config/wsgi.py restores the visitor's path in the public demo.
"""

from config.wsgi import application as app

__all__ = ["app"]
