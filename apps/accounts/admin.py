from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PatientDoctorAssignment, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_approved", "is_rejected", "is_active")
    list_filter = ("role", "is_approved", "is_rejected", "is_active")
    actions = ("approve_users",)

    fieldsets = UserAdmin.fieldsets + (
        ("CHA", {"fields": ("role", "is_approved", "is_rejected")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("CHA", {"fields": ("role", "is_approved", "is_rejected")}),
    )

    @admin.action(description="Approve selected users")
    def approve_users(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} user(s) approved.")


@admin.register(PatientDoctorAssignment)
class PatientDoctorAssignmentAdmin(admin.ModelAdmin):
    """Assign patients to doctors, which is what grants doctor-side access."""

    list_display = ("patient", "doctor", "is_active", "assigned_at")
    list_filter = ("is_active",)
    search_fields = ("patient__username", "doctor__username")
    autocomplete_fields = ("patient", "doctor")
    readonly_fields = ("assigned_at",)
