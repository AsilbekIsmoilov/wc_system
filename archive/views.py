"""
Archive ViewSet'y i statisticheskiy endpoint.
"""

from rest_framework import filters, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .filters import (
    ArchiveCompensationFilter,
    ArchiveCycleFilter,
    ArchiveEventLogFilter,
    ArchiveManualAdjustmentFilter,
    ArchiveOperatorSnapshotFilter,
    ArchiveTransferFilter,
    ArchiveWorkDebtDetailFilter,
    ArchiveWorkDebtFilter,
    ArchiveWorkLogDailyFilter,
)
from .models import (
    ArchiveCompensation,
    ArchiveCycle,
    ArchiveEventLog,
    ArchiveManualAdjustment,
    ArchiveOperatorSnapshot,
    ArchiveTransfer,
    ArchiveWorkDebt,
    ArchiveWorkDebtDetail,
    ArchiveWorkLogDaily,
)
from .permissions import ArchiveReadOnly, ArchiveStatistics
from .serializers import (
    ArchiveCompensationSerializer,
    ArchiveCycleSerializer,
    ArchiveEventLogSerializer,
    ArchiveManualAdjustmentSerializer,
    ArchiveOperatorSnapshotSerializer,
    ArchiveStatisticsQuerySerializer,
    ArchiveTransferSerializer,
    ArchiveWorkDebtDetailSerializer,
    ArchiveWorkDebtSerializer,
    ArchiveWorkLogDailySerializer,
)
from .services.scope import get_visible_operator_ids
from .services.statistics import StatisticsService


class ArchiveViewSetMixin:
    """
    Obshchiy mixin dlya vsekh archive ViewSet:
      - read-only
      - filtruet po vidimosti operatorov (operator/supervisor/manager)
      - ispolzuet bazu 'archive'
    """
    permission_classes = [ArchiveReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    def get_queryset(self):
        """Filtruem po vidimosti."""
        qs = super().get_queryset()

        # Esli year/month peredany — filtruem po vidimym operatoram
        year = self.request.query_params.get("archive_year")
        month = self.request.query_params.get("archive_month")

        if year and month:
            try:
                year_int = int(year)
                month_int = int(month)
                visible_ids = get_visible_operator_ids(
                    self.request.user, year_int, month_int,
                )
                if visible_ids is None:
                    return qs.none()
                qs = qs.filter(operator_id__in=visible_ids)
            except ValueError:
                return qs.none()

        return qs


class ArchiveCycleViewSet(viewsets.ReadOnlyModelViewSet):
    """Spisok zakrytykh tsiklov."""
    queryset = ArchiveCycle.objects.using("archive").all()
    serializer_class = ArchiveCycleSerializer
    permission_classes = [ArchiveReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ArchiveCycleFilter
    ordering_fields = ["year", "month", "closed_at"]
    ordering = ["-year", "-month"]


class ArchiveOperatorSnapshotViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveOperatorSnapshot.objects.using("archive").all()
    serializer_class = ArchiveOperatorSnapshotSerializer
    filterset_class = ArchiveOperatorSnapshotFilter
    search_fields = ["surname", "name", "operator_login"]
    ordering = ["surname", "name"]


class ArchiveWorkDebtViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveWorkDebt.objects.using("archive").all()
    serializer_class = ArchiveWorkDebtSerializer
    filterset_class = ArchiveWorkDebtFilter
    search_fields = ["operator_fio", "operator_login"]
    ordering = ["-final_debt"]


class ArchiveWorkDebtDetailViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveWorkDebtDetail.objects.using("archive").all()
    serializer_class = ArchiveWorkDebtDetailSerializer
    filterset_class = ArchiveWorkDebtDetailFilter
    search_fields = ["operator_fio", "operator_login", "note"]
    ordering = ["-day"]


class ArchiveWorkLogDailyViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveWorkLogDaily.objects.using("archive").all()
    serializer_class = ArchiveWorkLogDailySerializer
    filterset_class = ArchiveWorkLogDailyFilter
    search_fields = ["operator_fio", "operator_login"]
    ordering = ["-day"]


class ArchiveCompensationViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveCompensation.objects.using("archive").all()
    serializer_class = ArchiveCompensationSerializer
    filterset_class = ArchiveCompensationFilter
    search_fields = ["operator_fio", "operator_login", "comment", "type_display"]
    ordering = ["-planned_date"]


class ArchiveTransferViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveTransfer.objects.using("archive").all()
    serializer_class = ArchiveTransferSerializer
    filterset_class = ArchiveTransferFilter
    search_fields = ["operator_fio", "operator_login", "comment", "type_display"]
    ordering = ["-date_from"]


class ArchiveManualAdjustmentViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveManualAdjustment.objects.using("archive").all()
    serializer_class = ArchiveManualAdjustmentSerializer
    filterset_class = ArchiveManualAdjustmentFilter
    search_fields = ["operator_login", "field_name", "reason_text", "adjusted_by_username"]
    ordering = ["-adjusted_at"]


class ArchiveEventLogViewSet(ArchiveViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ArchiveEventLog.objects.using("archive").all()
    serializer_class = ArchiveEventLogSerializer
    filterset_class = ArchiveEventLogFilter
    search_fields = ["message", "operator_login"]
    ordering = ["-original_timestamp"]


# =============================================================================
# Statistics endpoint
# =============================================================================

class ArchiveStatisticsAPIView(APIView):
    """
    Statistika za konkretnyy zakrytyy tsikl.

    GET /api/v1/archive/statistics/?year=2026&month=5
    GET /api/v1/archive/statistics/?year=2026&month=5&group_id=3
    """
    permission_classes = [ArchiveStatistics]

    def get(self, request):
        serializer = ArchiveStatisticsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service = StatisticsService(
            year=data["year"],
            month=data["month"],
            user=request.user,
            group_id=data.get("group_id"),
        )
        return Response(service.collect())
