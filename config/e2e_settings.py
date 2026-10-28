"""Settings for the Playwright suite: pytest -m e2e --ds=config.e2e_settings --browser chromium.

Production security, except what an HTTP live server can't do: no HTTPS redirect, no Secure cookies.
The CSP is enforced (not report-only), so an inline script or style fails a test.
The design kit is on.
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
os.environ["DJANGO_SECURE_SSL_REDIRECT"] = "false"
os.environ["CSP_REPORT_ONLY"] = "false"
os.environ["DJANGO_KIT"] = "true"
# Playwright's sync API runs an event loop in the test thread; without this the ORM refuses to run.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from config.settings import *  # noqa: E402, F403

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
