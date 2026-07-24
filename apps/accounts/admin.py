from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_approved", "is_active")
    list_filter = ("role", "is_approved", "is_active")
    actions = ("approve_users",)

    fieldsets = UserAdmin.fieldsets + (
        ("CHA", {"fields": ("role", "is_approved")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("CHA", {"fields": ("role", "is_approved")}),
    )

    @admin.action(description="Approve selected users")
    def approve_users(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} user(s) approved.")
