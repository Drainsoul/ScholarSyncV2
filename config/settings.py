"""ScholarSync settings: one module, configured only through environment variables (spec §14)."""

import os
from pathlib import Path

from environs import Env

from config.hosts import vercel_hosts

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(os.environ.get("DJANGO_ENV_FILE", str(BASE_DIR / ".env")), recurse=False)

# Core ----------------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", False)
SECRET_KEY = env.str("DJANGO_SECRET_KEY")  # required: no fallback, ever

_vercel_hosts = vercel_hosts(os.environ)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", []) + _vercel_hosts
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in _vercel_hosts]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_vite",
    "csp",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.core.middleware.PermissionsPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = 0 if DEBUG else 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_SECURE = not DEBUG

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)

_CSP_DIRECTIVES = {
    "default-src": [SELF],
    "script-src": [SELF],
    "style-src": [SELF],
    "img-src": [SELF, "data:"],
    "font-src": [SELF],
    "connect-src": [SELF],
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
