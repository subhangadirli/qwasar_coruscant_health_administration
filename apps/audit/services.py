"""The one entry point for writing audit rows, so callers stay a one-liner."""

from .models import AuditLog


def record(action, actor=None, target="", detail=""):
    """Append an audit entry. `target`/`detail` are truncated to the column."""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        target=str(target)[:255],
        detail=str(detail)[:255],
    )
