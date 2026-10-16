from rest_framework.permissions import BasePermission

from .models import Role


def role_required(*roles):
    """Build a DRF permission that allows only active users with one of `roles`."""
    allowed = {str(r) for r in roles}

    class RolePermission(BasePermission):
        message = "আপনার এই কাজের অনুমতি নেই।"

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.is_active
                        and user.role in allowed)

    RolePermission.__name__ = "Is" + "Or".join(sorted(r.title() for r in allowed))
    return RolePermission


IsCitizen = role_required(Role.CITIZEN)
IsSurveyor = role_required(Role.SURVEYOR)
IsLandOfficer = role_required(Role.AC_LAND)
IsLawyer = role_required(Role.LAWYER)
IsSystemAdmin = role_required(Role.ADMIN)
# Anyone who may look up and verify records:
CanVerifyRecords = role_required(Role.CITIZEN, Role.SURVEYOR, Role.AC_LAND, Role.LAWYER, Role.ADMIN)
