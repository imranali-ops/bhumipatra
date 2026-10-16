from django.contrib import admin

from .models import MutationApplication, MutationDocument, MutationStep


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MutationApplication)
class ApplicationAdmin(ReadOnly):
    list_display = ("code", "status", "kind", "conflict_flag", "created_at")


@admin.register(MutationStep)
class StepAdmin(ReadOnly):
    list_display = ("application", "action", "to_status", "created_at")


@admin.register(MutationDocument)
class DocumentAdmin(ReadOnly):
    list_display = ("application", "kind", "original_name", "size", "created_at")
