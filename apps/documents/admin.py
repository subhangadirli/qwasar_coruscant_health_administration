from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "patient", "owner", "size", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("original_name", "patient__username", "owner__username")
    autocomplete_fields = ("patient", "owner")
    readonly_fields = ("checksum", "size", "uploaded_at")
