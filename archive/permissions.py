
from rest_framework.permissions import BasePermission, SAFE_METHODS


class ArchiveReadOnly(BasePermission):
    message = "Arkhiv tolko dlya chteniya."

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        return request.user.is_authenticated


class ArchiveStatistics(BasePermission):
    message = "Statistika nedostupna dlya operatorov."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ["supervisor", "manager", "admin"]
