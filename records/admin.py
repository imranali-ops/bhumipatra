from django.contrib import admin

from .models import Checkpoint, Owner, OwnershipEntry, Parcel


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records are created only through services.py so that hashing,
    signing and audit logging can never be bypassed from the admin site."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Parcel)
class ParcelAdmin(ReadOnlyAdmin):
    list_display = ("khatian_no", "dag_no", "mouza", "upazila", "district", "area_decimal")
    search_fields = ("khatian_no", "dag_no", "mouza")


@admin.register(Owner)
class OwnerAdmin(ReadOnlyAdmin):
    list_display = ("full_name", "nid_last4", "created_at")
    search_fields = ("full_name",)


@admin.register(OwnershipEntry)
class OwnershipEntryAdmin(ReadOnlyAdmin):
    list_display = ("parcel", "seq", "hash", "created_at")


@admin.register(Checkpoint)
class CheckpointAdmin(ReadOnlyAdmin):
    list_display = ("parcel", "seq", "head_hash", "key_id", "created_at")
