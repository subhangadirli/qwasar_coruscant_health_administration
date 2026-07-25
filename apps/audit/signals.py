"""Log successful logins off Django's built-in signal."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import AuditAction
from .services import record


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    record(AuditAction.LOGIN, actor=user, target=user.username)
