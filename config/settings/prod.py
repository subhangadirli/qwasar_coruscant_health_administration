"""Production settings. All secrets come from environment variables."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# ALLOWED_HOSTS, SECRET_KEY, DATABASE_URL, DOCUMENT_ENCRYPTION_KEY,
# CSRF_TRUSTED_ORIGINS are all read from the environment in base.py.

# Fail fast rather than silently signing sessions/CSRF tokens with the
# publicly-known scaffold default.
if SECRET_KEY == "django-insecure-change-me-in-prod":
    raise RuntimeError("SECRET_KEY must be set in production.")

# Security hardening.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Fail fast if the encryption key is missing in production.
if not env("DOCUMENT_ENCRYPTION_KEY"):
    raise RuntimeError("DOCUMENT_ENCRYPTION_KEY must be set in production.")
