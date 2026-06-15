"""
Классы прав доступа DRF для разных ролей.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOperator(BasePermission):
    """Только operator."""
    message = "Доступ только для операторов."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "operator"


class IsSupervisor(BasePermission):
    """Только supervisor."""
    message = "Доступ только для супервайзеров."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "supervisor"


class IsManager(BasePermission):
    """Только manager."""
    message = "Доступ только для менеджеров."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "manager"


class IsManagerOrAdmin(BasePermission):
    """Менеджер или администратор."""
    message = "Доступ только для менеджеров и администраторов."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["manager", "admin"]
        )


class IsSupervisorOrHigher(BasePermission):
    """Супервайзер или выше."""
    message = "Доступ только для супервайзеров, менеджеров и администраторов."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["supervisor", "manager", "admin"]
        )


class ReadOnlyOrManager(BasePermission):
    """
    Чтение — все аутентифицированные.
    Запись — только менеджер/админ.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in ["manager", "admin"]


class CanManualAdjust(BasePermission):
    """
    Право на ручную правку.
    Супервайзер может править свои группы.
    Менеджер/админ — что угодно.
    """
    message = "У вас нет прав на ручную правку."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["supervisor", "manager", "admin"]
        )


class CanCloseCycle(BasePermission):
    """Только менеджер/админ может вручную закрывать циклы."""
    message = "Закрывать циклы могут только менеджеры и администраторы."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["manager", "admin"]
        )