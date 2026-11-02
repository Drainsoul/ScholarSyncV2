"""Settings for pytest: exactly the production security configuration.

`config.settings` computes HSTS, secure cookies and the HTTPS redirect from DJANGO_DEBUG at import
time, so tests force DEBUG off *before* importing it (a local .env never overrides a variable that
is already set). The test client speaks HTTPS (see conftest.py) to match.
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
# Tests run in production mode, which refuses the .env.example placeholder key a dev .env holds.
os.environ["DJANGO_SECRET_KEY"] = "pytest-only-secret-key-" + "x" * 40
# Production mode requires the operator details (the privacy, terms and contact pages show them).
os.environ.setdefault("SITE_OPERATOR_NAME", "ScholarSync CI")
os.environ.setdefault("PRIVACY_CONTACT_EMAIL", "privacy@scholarsync.test")
# Production refuses an empty or wildcard host list.
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "scholarsync.example")

from config.settings import *  # noqa: E402, F403
