from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    """Administrators create officer accounts here and set their role."""
    list_display = ("username", "email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("ভূমিপত্র", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("ভূমিপত্র", {"fields": ("role",)}),)
