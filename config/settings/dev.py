"""Development settings."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# A stable dev key so migrations/sessions survive restarts without a .env.
SECRET_KEY = env("SECRET_KEY", "django-insecure-dev-key-not-for-production")

# Deterministic dev key for document encryption (override in .env if desired).
DOCUMENT_ENCRYPTION_KEY = env(
    "DOCUMENT_ENCRYPTION_KEY",
    "dGVzdC1kZXYta2V5LTMyLWJ5dGVzLWZvci1kZXYtb25seQ==",
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
