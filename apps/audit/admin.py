from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only view of the trail — entries are never added or changed here."""

    list_display = ("created_at", "actor", "action", "target", "detail")
    list_filter = ("action", "created_at")
    search_fields = ("target", "detail", "actor__username")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
