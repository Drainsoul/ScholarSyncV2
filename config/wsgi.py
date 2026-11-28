import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# The hosted demo's rewrite hides the visitor's path (branch `demo` only, config/rewrite_path.py).
if os.environ.get("SCHOLARSYNC_PUBLIC_DEMO", "").strip().lower() in {"true", "1", "yes", "on"}:
    from config.rewrite_path import restore_path

    application = restore_path(application)  # type: ignore[assignment]
