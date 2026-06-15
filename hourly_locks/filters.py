"""
Фильтры django-filter для DRF ViewSet'ов.
"""

import django_filters

from .models import (
    Compensation,
    EventLog,
    ManualAdjustment,
    OperatorScheduleDay,
    Transfer,
    WorkDebtDetail,
    WorkLogDaily,
)


class WorkDebtDetailFilter(django_filters.FilterSet):
    """Фильтры для записей долга."""
    day_from = django_filters.DateFilter(field_name="day", lookup_expr="gte")
    day_to = django_filters.DateFilter(field_name="day", lookup_expr="lte")
    cycle_year = django_filters.NumberFilter(field_name="cycle__year")
    cycle_month = django_filters.NumberFilter(field_name="cycle__month")
    has_debt = django_filters.BooleanFilter(method="filter_has_debt")

    class Meta:
        model = WorkDebtDetail
        fields = [
            "operator",
            "source",
            "violation_type",
            "locked_for_compensation",
        ]

    def filter_has_debt(self, queryset, name, value):
        from datetime import timedelta
        if value:
            return queryset.exclude(debt_full=timedelta(0), debt_lock=timedelta(0))
        return queryset.filter(debt_full=timedelta(0), debt_lock=timedelta(0))


class CompensationFilter(django_filters.FilterSet):
    """Фильтры для компенсаций."""
    planned_date_from = django_filters.DateFilter(
        field_name="planned_date", lookup_expr="gte",
    )
    planned_date_to = django_filters.DateFilter(
        field_name="planned_date", lookup_expr="lte",
    )
    created_at_from = django_filters.DateFilter(
        field_name="created_at", lookup_expr="gte",
    )
    created_at_to = django_filters.DateFilter(
        field_name="created_at", lookup_expr="lte",
    )
    type_code = django_filters.CharFilter(field_name="type_rule__code")
    cycle_year = django_filters.NumberFilter(field_name="cycle__year")
    cycle_month = django_filters.NumberFilter(field_name="cycle__month")

    class Meta:
        model = Compensation
        fields = [
            "operator",
            "type_rule",
            "status",
            "source",
            "deducted",
        ]


class TransferFilter(django_filters.FilterSet):
    """Фильтры для переносов/отгулов."""
    date_from_gte = django_filters.DateFilter(
        field_name="date_from", lookup_expr="gte",
    )
    date_from_lte = django_filters.DateFilter(
        field_name="date_from", lookup_expr="lte",
    )
    date_to_gte = django_filters.DateFilter(
        field_name="date_to", lookup_expr="gte",
    )
    date_to_lte = django_filters.DateFilter(
        field_name="date_to", lookup_expr="lte",
    )
    type_code = django_filters.CharFilter(field_name="type_rule__code")
    cycle_year = django_filters.NumberFilter(field_name="cycle__year")
    cycle_month = django_filters.NumberFilter(field_name="cycle__month")

    class Meta:
        model = Transfer
        fields = [
            "operator",
            "type_rule",
            "status",
        ]


class WorkLogDailyFilter(django_filters.FilterSet):
    """Фильтры для ежедневных логов."""
    day_from = django_filters.DateFilter(field_name="day", lookup_expr="gte")
    day_to = django_filters.DateFilter(field_name="day", lookup_expr="lte")
    shift_code = django_filters.CharFilter(field_name="shift__code")
    cycle_year = django_filters.NumberFilter(field_name="cycle__year")
    cycle_month = django_filters.NumberFilter(field_name="cycle__month")

    class Meta:
        model = WorkLogDaily
        fields = ["operator", "shift", "is_special_aggregation"]


class OperatorScheduleDayFilter(django_filters.FilterSet):
    """Фильтры для расписания."""
    day_from = django_filters.DateFilter(field_name="day", lookup_expr="gte")
    day_to = django_filters.DateFilter(field_name="day", lookup_expr="lte")
    shift_code = django_filters.CharFilter(field_name="shift__code")

    class Meta:
        model = OperatorScheduleDay
        fields = ["operator", "shift", "is_day_off", "source"]


class ManualAdjustmentFilter(django_filters.FilterSet):
    """Фильтры для ручных правок."""
    adjusted_at_from = django_filters.DateTimeFilter(
        field_name="adjusted_at", lookup_expr="gte",
    )
    adjusted_at_to = django_filters.DateTimeFilter(
        field_name="adjusted_at", lookup_expr="lte",
    )

    class Meta:
        model = ManualAdjustment
        fields = [
            "target_type",
            "operator",
            "reason_code",
            "adjusted_by",
        ]


class EventLogFilter(django_filters.FilterSet):
    """Фильтры для журнала событий."""
    timestamp_from = django_filters.DateTimeFilter(
        field_name="timestamp", lookup_expr="gte",
    )
    timestamp_to = django_filters.DateTimeFilter(
        field_name="timestamp", lookup_expr="lte",
    )

    class Meta:
        model = EventLog
        fields = [
            "event_type",
            "level",
            "operator",
            "target_type",
        ]