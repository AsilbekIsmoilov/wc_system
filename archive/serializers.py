"""
Serializatory dlya archive ViewSet'ov.
"""

from rest_framework import serializers

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


class ArchiveCycleSerializer(serializers.ModelSerializer):
    duration_days = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveCycle
        fields = "__all__"

    def get_duration_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return None


class ArchiveOperatorSnapshotSerializer(serializers.ModelSerializer):
    fio = serializers.CharField(read_only=True)

    class Meta:
        model = ArchiveOperatorSnapshot
        fields = "__all__"


class ArchiveWorkDebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveWorkDebt
        fields = "__all__"


class ArchiveWorkDebtDetailSerializer(serializers.ModelSerializer):
    total_debt = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveWorkDebtDetail
        fields = "__all__"

    def get_total_debt(self, obj):
        return str(obj.debt_full + obj.debt_lock)


class ArchiveWorkLogDailySerializer(serializers.ModelSerializer):
    net_duration = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveWorkLogDaily
        fields = "__all__"

    def get_net_duration(self, obj):
        from datetime import timedelta
        net = (obj.full_duration or timedelta(0)) - (obj.lock_duration or timedelta(0))
        return str(net) if net > timedelta(0) else "0:00:00"


class ArchiveCompensationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveCompensation
        fields = "__all__"


class ArchiveTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveTransfer
        fields = "__all__"


class ArchiveManualAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveManualAdjustment
        fields = "__all__"


class ArchiveEventLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveEventLog
        fields = "__all__"


# =============================================================================
# Serializatory dlya statistiki
# =============================================================================

class ArchiveStatisticsQuerySerializer(serializers.Serializer):
    """Vkhodnoy filter dlya statistiki."""
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    group_id = serializers.IntegerField(required=False, allow_null=True)


class StatItemSerializer(serializers.Serializer):
    """Format: {duration, count}."""
    duration = serializers.CharField(help_text="HH:MM:SS")
    count = serializers.IntegerField()


class ArchiveStatisticsResponseSerializer(serializers.Serializer):
    """Otvet statistiki."""
    cycle = ArchiveCycleSerializer(allow_null=True)
    total_operators = serializers.IntegerField()
    total_records = serializers.IntegerField()
    total_debt = StatItemSerializer()
    worked = StatItemSerializer()
    not_worked = StatItemSerializer()
    rejected_by_operator = StatItemSerializer()
    excluded = StatItemSerializer()
    types_summary = serializers.DictField()
    operators_table = serializers.ListField(
        child=serializers.DictField(),
    )
