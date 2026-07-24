from django.contrib import admin

from .models import Department, ServiceOrder


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("staff",)


@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = (
        "procedure",
        "patient",
        "doctor",
        "department",
        "priority",
        "status",
        "created_at",
    )
    list_filter = ("status", "priority", "department")
    search_fields = (
        "procedure",
        "notes",
        "patient__username",
        "doctor__username",
    )
    autocomplete_fields = ("patient", "doctor", "department")
    readonly_fields = ("created_at", "updated_at", "completed_at")
    date_hierarchy = "created_at"
