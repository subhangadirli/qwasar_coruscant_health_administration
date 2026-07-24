from django.contrib import admin

from .models import HealthReading


@admin.register(HealthReading)
class HealthReadingAdmin(admin.ModelAdmin):
    list_display = ("patient", "metric", "value", "unit", "recorded_at", "source")
    list_filter = ("metric", "source")
    search_fields = ("patient__username", "patient__email")
    date_hierarchy = "recorded_at"
    autocomplete_fields = ("patient",)
