"""Settings for pytest: exactly the production security configuration.

`config.settings` computes HSTS, secure cookies and the HTTPS redirect from DJANGO_DEBUG at import
time, so tests force DEBUG off *before* importing it (a local .env never overrides a variable that
is already set). The test client speaks HTTPS (see conftest.py) to match.
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
# Tests run in production mode, which refuses the .env.example placeholder key a dev .env holds.
os.environ["DJANGO_SECRET_KEY"] = "pytest-only-secret-key-" + "x" * 40

from config.settings import *  # noqa: E402, F403
