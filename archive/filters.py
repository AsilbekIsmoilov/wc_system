"""
Filtry dlya archive ViewSet'ov.
Glavnyy filter — po archive_year + archive_month (tsikl).
"""

import django_filters

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


class CycleArchiveFilterMixin(django_filters.FilterSet):
    """Obshchiy mixin dlya filtra po godu/mesyatsu arkhiva."""
    archive_year = django_filters.NumberFilter()
    archive_month = django_filters.NumberFilter()
    cycle_yyyymm = django_filters.CharFilter(method="filter_cycle_yyyymm")

    def filter_cycle_yyyymm(self, queryset, name, value):
        """Format: 2026-05"""
        try:
            year, month = value.split("-")
            return queryset.filter(archive_year=int(year), archive_month=int(month))
        except (ValueError, AttributeError):
            return queryset.none()


class ArchiveCompensationFilter(CycleArchiveFilterMixin):
    planned_date_from = django_filters.DateFilter(
        field_name="planned_date", lookup_expr="gte",
    )
    planned_date_to = django_filters.DateFilter(
        field_name="planned_date", lookup_expr="lte",
    )

    class Meta:
        model = ArchiveCompensation
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login",
            "group_id", "group_name",
            "type_code", "source", "status", "deducted",
        ]


class ArchiveTransferFilter(CycleArchiveFilterMixin):
    date_from_gte = django_filters.DateFilter(
        field_name="date_from", lookup_expr="gte",
    )
    date_from_lte = django_filters.DateFilter(
        field_name="date_from", lookup_expr="lte",
    )

    class Meta:
        model = ArchiveTransfer
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login",
            "group_id", "group_name",
            "type_code", "status", "was_split",
        ]


class ArchiveWorkDebtFilter(CycleArchiveFilterMixin):
    class Meta:
        model = ArchiveWorkDebt
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login",
            "group_id", "group_name",
        ]


class ArchiveWorkDebtDetailFilter(CycleArchiveFilterMixin):
    day_from = django_filters.DateFilter(field_name="day", lookup_expr="gte")
    day_to = django_filters.DateFilter(field_name="day", lookup_expr="lte")

    class Meta:
        model = ArchiveWorkDebtDetail
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login",
            "group_id", "group_name",
            "source", "shift_code", "violation_type",
        ]


class ArchiveWorkLogDailyFilter(CycleArchiveFilterMixin):
    day_from = django_filters.DateFilter(field_name="day", lookup_expr="gte")
    day_to = django_filters.DateFilter(field_name="day", lookup_expr="lte")

    class Meta:
        model = ArchiveWorkLogDaily
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login",
            "group_id", "shift_code",
        ]


class ArchiveCycleFilter(django_filters.FilterSet):
    year_from = django_filters.NumberFilter(field_name="year", lookup_expr="gte")
    year_to = django_filters.NumberFilter(field_name="year", lookup_expr="lte")

    class Meta:
        model = ArchiveCycle
        fields = ["year", "month"]


class ArchiveOperatorSnapshotFilter(CycleArchiveFilterMixin):
    class Meta:
        model = ArchiveOperatorSnapshot
        fields = [
            "archive_year", "archive_month",
            "operator_id", "operator_login", "group_id", "group_name",
        ]


class ArchiveManualAdjustmentFilter(CycleArchiveFilterMixin):
    class Meta:
        model = ArchiveManualAdjustment
        fields = [
            "archive_year", "archive_month",
            "target_type", "operator_id", "reason_code",
            "adjusted_by_id",
        ]


class ArchiveEventLogFilter(CycleArchiveFilterMixin):
    class Meta:
        model = ArchiveEventLog
        fields = [
            "archive_year", "archive_month",
            "event_type", "level", "operator_id",
        ]
