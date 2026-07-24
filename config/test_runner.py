"""Project test runner."""

from django.conf import settings
from django.test.runner import DiscoverRunner


class FastPasswordHasherRunner(DiscoverRunner):
    """Swap the slow production hasher for a fast one while testing.

    Nearly every test creates a user, and PBKDF2 is deliberately expensive,
    which dominated the suite's runtime. Hashing cost has no bearing on what
    these tests assert, so weaken it here and only here.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.PASSWORD_HASHERS = [
            "django.contrib.auth.hashers.MD5PasswordHasher",
        ]
