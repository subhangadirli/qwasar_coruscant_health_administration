from django.contrib import admin

from .models import DeviceToken, HealthReading, Report


@admin.register(HealthReading)
class HealthReadingAdmin(admin.ModelAdmin):
    list_display = ("patient", "metric", "value", "unit", "recorded_at", "source")
    list_filter = ("metric", "source")
    search_fields = ("patient__username", "patient__email")
    date_hierarchy = "recorded_at"
    autocomplete_fields = ("patient",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "patient", "doctor", "status", "published_at")
    list_filter = ("kind", "status")
    search_fields = ("title", "body", "patient__username", "doctor__username")
    autocomplete_fields = ("patient", "doctor")
    readonly_fields = ("created_at", "updated_at")
    actions = ("publish_reports",)

    @admin.action(description="Publish selected reports")
    def publish_reports(self, request, queryset):
        published = 0
        for report in queryset:
            if not report.is_published:
                report.publish()
                published += 1
        self.message_user(request, f"{published} report(s) published.")


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    """Audit and revoke device credentials.

    The token itself is unrecoverable by design, so there is nothing to edit
    here; deleting a row revokes the device's access.
    """

    list_display = ("patient", "created_at", "last_used_at")
    search_fields = ("patient__username", "patient__email")
    readonly_fields = ("patient", "key_hash", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False
