"""ScholarSync settings: one module, configured only through environment variables (spec §14)."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from environs import Env

from config.demo import demo_installed

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(os.environ.get("DJANGO_ENV_FILE", str(BASE_DIR / ".env")), recurse=False)

# Core ----------------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", False)
SECRET_KEY = env.str("DJANGO_SECRET_KEY")  # required: no fallback, ever


# Modes (open-source spec §6): developer = DEBUG, explore = localhost-only HTTP, else production.
EXPLORE = env.bool("SCHOLARSYNC_EXPLORE", False)
PRODUCTION = not DEBUG and not EXPLORE
EXPLORE_HOSTS = ["localhost", "127.0.0.1"]

if EXPLORE:
    if set(env.list("DJANGO_ALLOWED_HOSTS", [])) - set(EXPLORE_HOSTS):
        raise ImproperlyConfigured(
            "SCHOLARSYNC_EXPLORE only serves localhost and 127.0.0.1. "
            "To host ScholarSync, follow docs/HOSTING.md."
        )
    ALLOWED_HOSTS = list(EXPLORE_HOSTS)
else:
    ALLOWED_HOSTS = [h.strip() for h in env.list("DJANGO_ALLOWED_HOSTS", []) if h.strip()]
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
PRIVACY_NOTICE_VERSION = "2026-10-30"

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
    "django_vite",
    "csp",
    "template_partials",
    "apps.core",
    "apps.kit",
]

# The demo lives in one deletable folder (spec 2026-10-30 section 5). Absent folder, no demo.
# Production never installs it, so its templates and commands can't load even if the folder was
# left behind; core's deploy check (demo.E001) still fails while the folder exists.
DEMO_INSTALLED = demo_installed(BASE_DIR)
DEMO_ACTIVE = DEMO_INSTALLED and not PRODUCTION
if DEMO_ACTIVE:
    INSTALLED_APPS.append("apps.demo")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.core.middleware.PermissionsPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
            ],
        },
    },
]

# Database: Neon pooled URL at runtime, unpooled URL for migrations (build.py) ----------------
DATABASES = {
    "default": env.dj_db_url("DATABASE_URL", conn_max_age=0, conn_health_checks=True),
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# Email: one URL (smtp://user:pass@host:587, smtp+tls://..., console://) -----------------------
if not os.environ.get("EMAIL_URL"):
    os.environ.pop("EMAIL_URL", None)  # a blank line in .env means "use the console backend"
globals().update(env.dj_email_url("EMAIL_URL", "console://"))
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

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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

DJANGO_VITE = {
    "default": {
        "dev_mode": env.bool("VITE_DEV_MODE", False),
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
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_SECURE = PRODUCTION

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)


def _origin(url: str) -> str:
    """scheme://host[:port] of a URL, or "" when it has none."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


# Browsers talk to the storage origin directly (presigned PUT and GET).
_STORAGE_ORIGIN = _origin(S3_STORAGE["public_endpoint_url"] or S3_STORAGE["endpoint_url"])
_STORAGE_SOURCES = [_STORAGE_ORIGIN] if _STORAGE_ORIGIN else []

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
# Not a CSP_* setting name: django-csp 4 treats those as legacy config (csp.E001).
_csp_report_only = env.bool("CSP_REPORT_ONLY", True)
if _csp_report_only:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = {"DIRECTIVES": _CSP_DIRECTIVES}
else:
    CONTENT_SECURITY_POLICY = {"DIRECTIVES": _CSP_DIRECTIVES}

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
        environment=env.str("SENTRY_ENVIRONMENT", "production" if PRODUCTION else "local"),
        release=env.str("SENTRY_RELEASE", "") or None,
    )
