from rest_framework import permissions


class IsStaffUser(permissions.BasePermission):
    """Staff: Django staff/superuser or linked institutions.Employee."""

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.is_superuser or u.is_staff:
            return True
        return hasattr(u, "employee_profile")


class IsCustomerUser(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and hasattr(u, "customer_profile")
