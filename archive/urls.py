"""
URL marshruty archive app.

Vse marshrutuyutsya cherez core/urls.py s prefiksom /api/archive/v1/.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ArchiveCompensationViewSet,
    ArchiveCycleViewSet,
    ArchiveEventLogViewSet,
    ArchiveManualAdjustmentViewSet,
    ArchiveOperatorSnapshotViewSet,
    ArchiveStatisticsAPIView,
    ArchiveTransferViewSet,
    ArchiveWorkDebtDetailViewSet,
    ArchiveWorkDebtViewSet,
    ArchiveWorkLogDailyViewSet,
)

router = DefaultRouter()
router.register(r"cycles", ArchiveCycleViewSet, basename="archive-cycles")
router.register(r"operator-snapshots", ArchiveOperatorSnapshotViewSet,
                basename="archive-operator-snapshots")
router.register(r"work-debts", ArchiveWorkDebtViewSet, basename="archive-work-debts")
router.register(r"work-debt-details", ArchiveWorkDebtDetailViewSet,
                basename="archive-work-debt-details")
router.register(r"work-logs-daily", ArchiveWorkLogDailyViewSet,
                basename="archive-work-logs-daily")
router.register(r"compensations", ArchiveCompensationViewSet,
                basename="archive-compensations")
router.register(r"transfers", ArchiveTransferViewSet, basename="archive-transfers")
router.register(r"manual-adjustments", ArchiveManualAdjustmentViewSet,
                basename="archive-manual-adjustments")
router.register(r"event-logs", ArchiveEventLogViewSet, basename="archive-event-logs")


urlpatterns = [
    path("api/v1/archive/", include(router.urls)),
    path(
        "api/v1/archive/statistics/",
        ArchiveStatisticsAPIView.as_view(),
        name="archive-statistics",
    ),
]
