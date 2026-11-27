"""ScholarSync settings: one module, configured only through environment variables (spec §14)."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import dj_email_url
from django.core.exceptions import ImproperlyConfigured
from environs import Env

from config.demo import demo_installed

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(os.environ.get("DJANGO_ENV_FILE", str(BASE_DIR / ".env")), recurse=False)

# Core ----------------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", False)
SECRET_KEY = env.str("DJANGO_SECRET_KEY")  # required: no fallback, ever
# Old keys kept while a rotation settles: they still verify sessions and decrypt 2FA secrets.
SECRET_KEY_FALLBACKS: list[str] = env.list("DJANGO_SECRET_KEY_FALLBACKS", [])


# Modes (open-source spec §6): developer = DEBUG, explore = localhost-only HTTP, else production.
EXPLORE = env.bool("SCHOLARSYNC_EXPLORE", False)
PRODUCTION = not DEBUG and not EXPLORE
EXPLORE_HOSTS = ["localhost", "127.0.0.1"]

# Public demo (branch `demo` only, docs/design/2026-11-28-hosted-demo-design.md section 5.1):
# production's security with the demo switched on, email printed instead of sent, and staff 2FA off.
# PRODUCTION stays true, so every production check below still applies unless it names this flag.
PUBLIC_DEMO = env.bool("SCHOLARSYNC_PUBLIC_DEMO", False)
if PUBLIC_DEMO and not PRODUCTION:
    raise ImproperlyConfigured(
        "SCHOLARSYNC_PUBLIC_DEMO can't be combined with DJANGO_DEBUG or SCHOLARSYNC_EXPLORE."
    )
# Vercel Cron signs its calls with this; the reset endpoint compares it (design section 5.4).
CRON_SECRET = env.str("CRON_SECRET", "") if PUBLIC_DEMO else ""
if PUBLIC_DEMO and len(CRON_SECRET) < 32:
    raise ImproperlyConfigured(
        "CRON_SECRET must be at least 32 characters in the public demo (docs/hosted-demo.md)."
    )

if EXPLORE:
    if set(env.list("DJANGO_ALLOWED_HOSTS", [])) - set(EXPLORE_HOSTS):
        raise ImproperlyConfigured(
            "SCHOLARSYNC_EXPLORE only serves localhost and 127.0.0.1. "
            "To host ScholarSync, follow docs/HOSTING.md."
        )
    ALLOWED_HOSTS = list(EXPLORE_HOSTS)
else:
    _hosts: list[str] = env.list("DJANGO_ALLOWED_HOSTS", [])
    ALLOWED_HOSTS = [h.strip() for h in _hosts if h.strip()]
    if PRODUCTION and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must list your host names in production: not empty, no '*'. "
            "See docs/HOSTING.md."
        )
# Explore trusts no extra origins (only the Codespaces one below may be added).
CSRF_TRUSTED_ORIGINS: list[str] = [] if EXPLORE else env.list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

# GitHub Codespaces (explore only): its proxy forwards https://<name>-<port>.<domain> to the app.
_codespace_name = env.str("CODESPACE_NAME", "")
_codespace_domain = env.str("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "")
if EXPLORE and _codespace_name and _codespace_domain:
    _codespace_host = f"{_codespace_name}-{env.int('APP_PORT', 8000)}.{_codespace_domain}"
    ALLOWED_HOSTS.append(_codespace_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_codespace_host}")
    # A codespace is reachable over the internet (signed in to GitHub), so the public key would
    # let anyone who can open the forwarded port forge sessions.
    if SECRET_KEY.startswith("explore-only-"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is the public explore key, which a codespace must not use. "
            "The devcontainer generates a key for each codespace; see docs/SETUP.md."
        )

if PRODUCTION and SECRET_KEY.startswith("explore-only-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is the public explore key. "
        "Set your own secret key for production (docs/HOSTING.md)."
    )

if PRODUCTION and SECRET_KEY.startswith("local-dev-only-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is the .env.example placeholder. "
        "Generate your own secret key for production (docs/HOSTING.md)."
    )

# The public address of this copy, for links in emails sent outside a request (spec section 10).
# Blank: the first allowed host over https in production, else the local address. Never taken
# from a request, so a forged Host header cannot point an emailed link elsewhere.
SITE_URL = env.str("SITE_URL", "").strip().rstrip("/")
if PRODUCTION:
    if not SITE_URL and (not ALLOWED_HOSTS or ALLOWED_HOSTS[0].startswith(".")):
        raise ImproperlyConfigured(
            "Set SITE_URL (for example https://scholarships.example.org) because the first "
            "DJANGO_ALLOWED_HOSTS entry is a wildcard that is no link (docs/HOSTING.md)."
        )
    if SITE_URL and not SITE_URL.startswith("https://"):
        raise ImproperlyConfigured(
            "SITE_URL must start with https:// in production (docs/HOSTING.md)."
        )
if not SITE_URL:
    SITE_URL = (
        f"https://{ALLOWED_HOSTS[0]}"
        if PRODUCTION and ALLOWED_HOSTS
        else f"http://127.0.0.1:{env.int('APP_PORT', 8000)}"
    )

# Who runs this copy (open-source spec section 15). Required in production: the privacy, terms and
# contact pages name the operator, and a host must decide who that is. Explore and developer
# copies run on the visitor's own computer.
SITE_OPERATOR_NAME = (
    env.str("SITE_OPERATOR_NAME")
    if PRODUCTION
    else env.str("SITE_OPERATOR_NAME", "This local copy")
)
PRIVACY_CONTACT_EMAIL = (
    env.str("PRIVACY_CONTACT_EMAIL") if PRODUCTION else env.str("PRIVACY_CONTACT_EMAIL", "")
)
_PLACEHOLDER_HELP = "Set it to your real value in .env (docs/HOSTING.md)."
if PRODUCTION:
    if not SITE_OPERATOR_NAME.strip() or "change-me" in SITE_OPERATOR_NAME.lower():
        raise ImproperlyConfigured(
            f"SITE_OPERATOR_NAME is blank or a placeholder. {_PLACEHOLDER_HELP}"
        )
    _email = PRIVACY_CONTACT_EMAIL.strip().lower()
    _domain = _email.rpartition("@")[2]
    if (
        not _email
        or "change-me" in _email
        or "@" not in _email
        or any(part == "example" for part in _domain.split("."))
        or _domain in {"example.com", "example.org", "example.net"}
    ):
        raise ImproperlyConfigured(
            f"PRIVACY_CONTACT_EMAIL is blank or a placeholder. {_PLACEHOLDER_HELP}"
        )
# The privacy notice version. M4's ConsentRecord.notice_version stores it; bump it on changes.
PRIVACY_NOTICE_VERSION = "2026-11-19"

# Design kit (spec §12): /_kit/ answers 404 unless enabled, and is never allowed in production.
KIT_ENABLED = env.bool("DJANGO_KIT", DEBUG or EXPLORE)
if KIT_ENABLED and PRODUCTION:
    raise ImproperlyConfigured("DJANGO_KIT must be off in production. It is for local use only.")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.mfa",
    "allauth.usersessions",
    "allauth.socialaccount.providers.google",
    "django_vite",
    "csp",
    "template_partials",
    "apps.accounts",
    "apps.core",
    "apps.programs",
    "apps.files",
    "apps.students",
    "apps.applications",
    "apps.awards",
    "apps.money",
    "apps.matching",
    "apps.workspace",
    "apps.reports",
    "apps.office",
    "apps.kit",
]

# The demo lives in one deletable folder (spec 2026-10-30 section 5). Absent folder, no demo.
# Production never installs it, so its templates and commands can't load even if the folder was
# left behind; core's deploy check (demo.E001) still fails while the folder exists.
DEMO_INSTALLED = demo_installed(BASE_DIR)
DEMO_ACTIVE = DEMO_INSTALLED and (not PRODUCTION or PUBLIC_DEMO)
if DEMO_ACTIVE:
    INSTALLED_APPS.append("apps.demo")

MIDDLEWARE = [
    "apps.core.request_context.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.core.middleware.PermissionsPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.NoStoreMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.accounts.mfa_policy.RequireStaffMfaMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.session_policy.SessionPolicyMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if PUBLIC_DEMO:
    # Shared test accounts: their credentials, emails and 2FA can't be changed (design 5.2).
    MIDDLEWARE.insert(
        MIDDLEWARE.index("apps.accounts.mfa_policy.RequireStaffMfaMiddleware") + 1,
        "apps.demo.lockdown.PublicDemoLockdownMiddleware",
    )

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.account_shell",
                "apps.accounts.theme.theme",
            ],
        },
    },
]

# Database: any PostgreSQL 17 URL (docker/entrypoint.sh migrates via DATABASE_URL_UNPOOLED if set) -
DATABASES = {
    "default": env.dj_db_url("DATABASE_URL", conn_max_age=0, conn_health_checks=True),
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# Email: one URL (submission://user:pass@host:587, smtp://...:465?ssl=true, console://) ---------
# Read through `env`, never os.environ: environs keeps the .env file's values in its own store.
_email_url = env.str("EMAIL_URL", "").strip()
if PRODUCTION and not PUBLIC_DEMO and not _email_url:
    raise ImproperlyConfigured(
        "EMAIL_URL is blank. Production needs a real SMTP server, or reset and verification "
        "links would be written to the log. See docs/HOSTING.md."
    )
# A blank line in .env means "use the console backend".
_email_config = dj_email_url.parse(_email_url or "console://")
if "EMAIL_BACKEND" not in _email_config:
    # dj-email-url ignores schemes it doesn't know (smtp+tls://, for one) and returns no backend.
    raise ImproperlyConfigured(
        "EMAIL_URL's scheme isn't recognised. Use submission:// (STARTTLS, port 587), "
        "smtp://...:465?ssl=true (implicit TLS) or smtp:// (unencrypted). See .env.example."
    )
globals().update(_email_config)
# Backends that never deliver: they would print links into the log or drop mail while every
# outbox row reads "sent".
_UNDELIVERED_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
}
if PRODUCTION and not PUBLIC_DEMO and _email_config["EMAIL_BACKEND"] in _UNDELIVERED_EMAIL_BACKENDS:
    raise ImproperlyConfigured(
        "EMAIL_URL must point at a real SMTP server in production, not a console, memory or "
        "dummy backend. See docs/HOSTING.md."
    )
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", "ScholarSync <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# File storage: any S3-compatible service (consumed by apps/files in M5) -------------------------
S3_STORAGE: dict[str, str] = {
    "endpoint_url": env.str("S3_ENDPOINT_URL", ""),
    "public_endpoint_url": env.str("S3_PUBLIC_ENDPOINT_URL", ""),
    "region": env.str("S3_REGION", ""),
    "bucket": env.str("S3_BUCKET", ""),
    "access_key_id": env.str("S3_ACCESS_KEY_ID", ""),
    "secret_access_key": env.str("S3_SECRET_ACCESS_KEY", ""),
    "addressing_style": env.str("S3_ADDRESSING_STYLE", "path"),
}
# The compose storage service's key is public (it is in compose.yaml and .env.example).
if PRODUCTION and S3_STORAGE["secret_access_key"] == "scholarsync-explore-secret":  # noqa: S105
    raise ImproperlyConfigured(
        "S3_SECRET_ACCESS_KEY is the public explore storage key. "
        "Use your own storage keys in production (docs/HOSTING.md)."
    )

# Optional malware scanning (spec §10, M13): with a host, upload confirm streams each file to
# clamd and refuses it while clamd is down; unset, nothing is scanned.
CLAMAV_HOST = env.str("CLAMAV_HOST", "")
CLAMAV_PORT = env.int("CLAMAV_PORT", 3310)

# Unencrypted connections to other machines (spec §10, M13).
ALLOW_PLAINTEXT_SERVICES = env.bool("ALLOW_PLAINTEXT_SERVICES", False)
if PRODUCTION and not ALLOW_PLAINTEXT_SERVICES:
    from config.plaintext import plaintext_refusals  # noqa: E402

    _refusals = plaintext_refusals(
        database_url=env.str("DATABASE_URL", ""),
        email_url=_email_url,
        storage_urls={
            "S3_ENDPOINT_URL": S3_STORAGE["endpoint_url"],
            "S3_PUBLIC_ENDPOINT_URL": S3_STORAGE["public_endpoint_url"],
        },
        clamav_host=CLAMAV_HOST,
    )
    if _refusals:
        raise ImproperlyConfigured(" ".join(_refusals))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Accounts (django-allauth): email login, verified before first sign-in, students only ----------
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
# Password, authenticator code, or a code emailed to a verified address (rev 39). Named here so a
# change to allauth's default can't quietly add or drop one.
ACCOUNT_REAUTHENTICATION_METHODS = ["password", "code", "mfa"]
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
# Two-factor sign-in (spec §10, M13): TOTP and recovery codes; required for staff and the office
# in production, off in developer and explore modes so the demo keeps one-click sign-in.
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_ADAPTER = "apps.accounts.adapters.MFAAdapter"
# The session list at /accounts/sessions/ (M13); no per-request activity writes.
USERSESSIONS_TRACK_ACTIVITY = False
MFA_TOTP_ISSUER = "ScholarSync"
# Production only, so a .env copied from .env.example never forces it on a developer copy.
# The public demo turns it off: its shared staff accounts have no authenticator and may not add one.
MFA_REQUIRED_FOR_STAFF = PRODUCTION and not PUBLIC_DEMO and env.bool("MFA_REQUIRED_FOR_STAFF", True)
ACCOUNT_FORMS = {"signup": "apps.accounts.forms.SignupForm"}
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_FORMS = {"signup": "apps.accounts.forms.SocialSignupForm"}
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# How many reverse proxies sit in front of the app (0 = none). Rate limits key on the client IP.
# Blank means the default (compose.production.yaml then supplies 1).
_trusted_proxy_count = env.str("TRUSTED_PROXY_COUNT", "").strip()
ALLAUTH_TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT") if _trusted_proxy_count else 0
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "core:home"  # the adapter sends each role to its own home
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
# Only students sign up, and the post-verification login follows this URL, not the adapter.
ACCOUNT_SIGNUP_REDIRECT_URL = "students:home"

# Google sign-in is offered only when both values are set.
_GOOGLE_CLIENT_ID = env.str("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = env.str("GOOGLE_CLIENT_SECRET", "")
SOCIALACCOUNT_PROVIDERS: dict[str, object] = (
    {
        "google": {
            "APPS": [{"client_id": _GOOGLE_CLIENT_ID, "secret": _GOOGLE_CLIENT_SECRET}],
            "SCOPE": ["profile", "email"],
        }
    }
    if _GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET
    else {}
)

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "apps.accounts.validators.SiteWordsValidator"},
]
# Breached-password check (spec §10, M13): Have I Been Pwned's k-anonymity range API, production
# only (developer and explore copies may be offline); fails open.
PASSWORD_BREACH_CHECK = PRODUCTION and env.bool("PASSWORD_BREACH_CHECK", True)
if PASSWORD_BREACH_CHECK:
    AUTH_PASSWORD_VALIDATORS.append({"NAME": "apps.accounts.breach.BreachedPasswordValidator"})

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

from django.contrib.messages import constants as message_constants  # noqa: E402

# Toast tones (templates/components/toast.html) use "danger", not Django's "error".
MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# Static files: Vite builds into static/dist; WhiteNoise's manifest storage hashes everything --
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# The Vite dev server serves scripts from its own origin, so the CSP is report-only with it.
VITE_DEV_MODE = env.bool("VITE_DEV_MODE", False)
DJANGO_VITE = {
    "default": {
        "dev_mode": VITE_DEV_MODE,
        "manifest_path": BASE_DIR / "static" / "dist" / ".vite" / "manifest.json",
        "static_url_prefix": "dist",
    }
}

# Security (spec §10) -------------------------------------------------------------------------
from csp.constants import NONE, SELF  # noqa: E402

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31_536_000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION
# Preload is a one-way commitment for the whole domain; decide at launch (spec §10, M12).
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 12 * 60 * 60  # also the absolute limit from sign-in (M13)
# Idle limits (spec §10, M13): staff and the office handle many people's data.
SESSION_IDLE_MINUTES_STAFF = env.float("SESSION_IDLE_MINUTES_STAFF", 30)
SESSION_IDLE_MINUTES_STUDENT = env.float("SESSION_IDLE_MINUTES_STUDENT", 60)
CSRF_COOKIE_SECURE = PRODUCTION
# htmx sends the token from `hx-headers` on <body>; no script reads the cookie (ASVS V3.3.4).
CSRF_COOKIE_HTTPONLY = True
# `__Host-` cookies are HTTPS-only and bound to this host (ASVS V3.3.1, V3.3.3); browsers refuse
# them over plain HTTP, so only production uses the prefix.
SESSION_COOKIE_NAME = "__Host-sessionid" if PRODUCTION else "sessionid"
CSRF_COOKIE_NAME = "__Host-csrftoken" if PRODUCTION else "csrftoken"
# The light/dark choice from the account menu (spec §12 rev 29; apps/accounts/theme.py).
THEME_COOKIE_NAME = "__Host-theme" if PRODUCTION else "theme"
# Flash messages live in the session: no separate messages cookie.
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)


def _storage_sources() -> list[str]:
    """Origins browsers use for presigned PUT and GET: path style is the endpoint itself,
    virtual style is the bucket's own subdomain of it."""
    endpoint = urlsplit(S3_STORAGE["public_endpoint_url"] or S3_STORAGE["endpoint_url"])
    if not (endpoint.scheme and endpoint.netloc):
        return []
    if S3_STORAGE["addressing_style"] == "virtual" and S3_STORAGE["bucket"]:
        return [f"{endpoint.scheme}://{S3_STORAGE['bucket']}.{endpoint.netloc}"]
    return [f"{endpoint.scheme}://{endpoint.netloc}"]


_STORAGE_SOURCES = _storage_sources()

_CSP_DIRECTIVES = {
    "default-src": [SELF],
    "script-src": [SELF],
    "style-src": [SELF],
    "img-src": [SELF, "data:", *_STORAGE_SOURCES],
    "font-src": [SELF],
    "connect-src": [SELF, *_STORAGE_SOURCES],
    "frame-ancestors": [NONE],
    "form-action": [SELF],
    "base-uri": [SELF],
    "object-src": [NONE],
}
# Google sign-in posts a form to /accounts/google/login/, which redirects to Google; browsers apply
# form-action to that redirect, so Google is allowed there only when sign-in with Google is on.
if SOCIALACCOUNT_PROVIDERS:
    _CSP_DIRECTIVES["form-action"] = [SELF, "https://accounts.google.com"]
# Not a CSP_* setting name: django-csp 4 treats those as legacy config (csp.E001).
# Enforced by default (M12); report-only only with the Vite dev server or while debugging. No
# report-uri: browsers would post full page URLs and Referers straight to Sentry, past scrub_event.
_csp_report_only = env.bool("CSP_REPORT_ONLY", False) or VITE_DEV_MODE
_csp_policy = {"DIRECTIVES": _CSP_DIRECTIVES}
CONTENT_SECURITY_POLICY = None if _csp_report_only else _csp_policy
CONTENT_SECURITY_POLICY_REPORT_ONLY = _csp_policy if _csp_report_only else None

# Logging and errors (spec §10) ---------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["stdout"], "level": env.str("LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

SENTRY_DSN = env.str("SENTRY_DSN", "")
if SENTRY_DSN:
    from apps.core.sentry import init_sentry

    init_sentry(
        dsn=SENTRY_DSN,
        # Blank (as in .env.example) means the mode's default.
        environment=env.str("SENTRY_ENVIRONMENT", "") or ("production" if PRODUCTION else "local"),
        release=env.str("SENTRY_RELEASE", "") or None,
    )
