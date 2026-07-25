"""An append-only audit trail for security-sensitive actions.

Every entry records who did what to which object and when. Rows are written
through `apps.audit.services.record` (and the login signal in `signals.py`);
they are never edited or deleted through the app — the admin registration is
read-only — so the log stays trustworthy after the fact.
"""

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN = "login", "Login"
    USER_APPROVED = "user_approved", "User approved"
    USER_REJECTED = "user_rejected", "User rejected"
    REPORT_PUBLISHED = "report_published", "Report published"
    DOCUMENT_DOWNLOADED = "document_downloaded", "Document downloaded"
    EMERGENCY_INTAKE = "emergency_intake", "Emergency intake"


class AuditLog(models.Model):
    # SET_NULL so an actor account can be removed without erasing the history
    # of what they did.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices)
    target = models.CharField(
        max_length=255, blank=True, help_text="What the action was performed on."
    )
    detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["action", "-created_at"])]

    def __str__(self):
        who = self.actor.username if self.actor else "system"
        return f"{who} · {self.get_action_display()} · {self.target}"
