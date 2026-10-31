"""Settings for the Playwright suite: pytest -m e2e --ds=config.e2e_settings --browser chromium.

Explore mode: localhost-only HTTP, no HTTPS redirect, no Secure cookies.
The CSP is enforced (not report-only), so an inline script or style fails a test.
The design kit is on (explore mode enables it).
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
os.environ["SCHOLARSYNC_EXPLORE"] = "true"
os.environ["CSP_REPORT_ONLY"] = "false"
# Playwright's sync API runs an event loop in the test thread; without this the ORM refuses to run.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from config.settings import *  # noqa: E402, F403

STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
