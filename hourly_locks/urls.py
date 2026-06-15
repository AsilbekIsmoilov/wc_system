from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AutomationOverrideViewSet,
    CompensationViewSet,
    CycleViewSet,
    EventLogViewSet,
    GroupViewSet,
    ManualAdjustmentViewSet,
    MeView,
    MyTokenObtainPairView,
    NoteViewSet,
    OperatorScheduleDayViewSet,
    OperatorViewSet,
    RequestTypeRuleViewSet,
    RetroactiveCompensationCheckView,
    ShiftViewSet,
    SystemPolicyViewSet,
    TransferViewSet,
    WorkDebtDetailViewSet,
    WorkDebtViewSet,
    WorkLogDailyViewSet,
)

router = DefaultRouter()

# Основные ресурсы
router.register(r"operators", OperatorViewSet, basename="operators")
router.register(r"groups", GroupViewSet, basename="groups")

# Расписание и смены
router.register(r"shifts", ShiftViewSet, basename="shifts")
router.register(
    r"operator-schedule-days",
    OperatorScheduleDayViewSet,
    basename="operator-schedule-days",
)

# Циклы
router.register(r"cycles", CycleViewSet, basename="cycles")

# Конфигурация (только для admin/manager)
router.register(
    r"request-type-rules",
    RequestTypeRuleViewSet,
    basename="request-type-rules",
)
router.register(r"system-policies", SystemPolicyViewSet, basename="system-policies")

# Логи и долги
router.register(r"work-logs-daily", WorkLogDailyViewSet, basename="work-logs-daily")
router.register(r"work-debts", WorkDebtViewSet, basename="work-debts")
router.register(
    r"work-debt-details",
    WorkDebtDetailViewSet,
    basename="work-debt-details",
)

# Заявки
router.register(r"compensations", CompensationViewSet, basename="compensations")
router.register(r"transfers", TransferViewSet, basename="transfers")

# Человеческий фактор
router.register(
    r"manual-adjustments",
    ManualAdjustmentViewSet,
    basename="manual-adjustments",
)
router.register(
    r"automation-overrides",
    AutomationOverrideViewSet,
    basename="automation-overrides",
)
router.register(r"notes", NoteViewSet, basename="notes")

router.register(r"event-logs", EventLogViewSet, basename="event-logs")


urlpatterns = [
    path("api/v1/", include(router.urls)),

    path(
        "api/v1/auth/token/",
        MyTokenObtainPairView.as_view(),
        name="auth_token",
    ),
    path(
        "api/v1/auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="auth_token_refresh",
    ),
    path("api/v1/auth/me/", MeView.as_view(), name="auth_me"),

    path(
        "api/v1/compensations/retroactive-check/",
        RetroactiveCompensationCheckView.as_view(),
        name="retroactive-check",
    ),

    # OpenAPI / Swagger
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/docs/swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger",
    ),
    path(
        "api/v1/docs/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]