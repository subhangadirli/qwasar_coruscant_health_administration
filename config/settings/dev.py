"""Development settings."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# A stable dev key so migrations/sessions survive restarts without a .env.
SECRET_KEY = env("SECRET_KEY", "django-insecure-dev-key-not-for-production")

# Deterministic dev key for document encryption (override in .env if desired).
# Must decode to exactly 32 bytes for Fernet; generate a new one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DOCUMENT_ENCRYPTION_KEY = env(
    "DOCUMENT_ENCRYPTION_KEY",
    "yqT6ddaLeFPFH_fSVQ1vlnpXK3FHNj1_8PT31Zui_1A=",
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
