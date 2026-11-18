"""Settings for pytest: exactly the production security configuration.

`config.settings` computes HSTS, secure cookies and the HTTPS redirect from DJANGO_DEBUG at import
time, so tests force DEBUG off *before* importing it (a local .env never overrides a variable that
is already set). The test client speaks HTTPS (see conftest.py) to match.
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
# Tests run in production mode, which refuses the .env.example placeholder key a dev .env holds.
os.environ["DJANGO_SECRET_KEY"] = "pytest-only-secret-key-" + "x" * 40
# Production mode also refuses the public explore storage secret that .env.example holds.
os.environ["S3_SECRET_ACCESS_KEY"] = "pytest-only-storage-secret"  # noqa: S105
# Production mode requires the operator details (the privacy, terms and contact pages show them).
os.environ.setdefault("SITE_OPERATOR_NAME", "ScholarSync CI")
os.environ.setdefault("PRIVACY_CONTACT_EMAIL", "privacy@scholarsync.test")
# Production refuses an empty or wildcard host list.
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "scholarsync.example")
# Production refuses a blank or console EMAIL_URL. Nothing connects to it: pytest-django swaps in
# the locmem backend for every test (the `mailoutbox` fixture reads it).
os.environ.setdefault("EMAIL_URL", "smtp://localhost:25")
# The CSP as production enforces it, whatever a local .env says (a debugging host may set true).
os.environ["CSP_REPORT_ONLY"] = "false"

from config.settings import *  # noqa: E402, F403

# Rate limits (allauth) need a cache and tests have no cache table.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
