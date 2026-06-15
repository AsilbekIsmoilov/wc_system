"""
Django admin dlya archive — VSE READ-ONLY.
"""

from django.contrib import admin

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


class ReadOnlyAdminMixin:
    """Zapreshchaet add/change/delete cherez admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArchiveCycle)
class ArchiveCycleAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("year", "month", "start_date", "end_date",
                    "closed_at", "closed_by_username")
    list_filter = ("year", "month")
    search_fields = ("year",)
    ordering = ("-year", "-month")


@admin.register(ArchiveOperatorSnapshot)
class ArchiveOperatorSnapshotAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_id",
                    "operator_login", "surname", "name", "group_name")
    list_filter = ("archive_year", "archive_month", "group_name")
    search_fields = ("operator_login", "surname", "name")


@admin.register(ArchiveWorkDebt)
class ArchiveWorkDebtAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_login",
                    "operator_fio", "group_name", "final_debt",
                    "total_accumulated")
    list_filter = ("archive_year", "archive_month", "group_name")
    search_fields = ("operator_login", "operator_fio")
    ordering = ("-final_debt",)


@admin.register(ArchiveWorkDebtDetail)
class ArchiveWorkDebtDetailAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_login",
                    "day", "source", "shift_code", "debt_full", "debt_lock")
    list_filter = ("archive_year", "archive_month", "source", "shift_code")
    search_fields = ("operator_login", "operator_fio", "note")
    date_hierarchy = "day"


@admin.register(ArchiveWorkLogDaily)
class ArchiveWorkLogDailyAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_login",
                    "day", "shift_code", "full_duration", "lock_duration")
    list_filter = ("archive_year", "archive_month", "shift_code")
    search_fields = ("operator_login", "operator_fio")
    date_hierarchy = "day"


@admin.register(ArchiveCompensation)
class ArchiveCompensationAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_login",
                    "planned_date", "type_code", "source", "status",
                    "requested_duration", "deducted")
    list_filter = ("archive_year", "archive_month", "type_code",
                   "source", "status", "deducted")
    search_fields = ("operator_login", "operator_fio", "comment")
    date_hierarchy = "planned_date"


@admin.register(ArchiveTransfer)
class ArchiveTransferAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "operator_login",
                    "type_code", "status", "date_from", "date_to",
                    "requested_duration", "was_split")
    list_filter = ("archive_year", "archive_month", "type_code",
                   "status", "was_split")
    search_fields = ("operator_login", "operator_fio", "comment")
    date_hierarchy = "date_from"


@admin.register(ArchiveManualAdjustment)
class ArchiveManualAdjustmentAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "target_type",
                    "target_id", "field_name", "operator_login",
                    "reason_code", "adjusted_by_username", "adjusted_at")
    list_filter = ("archive_year", "archive_month", "target_type", "reason_code")
    search_fields = ("operator_login", "field_name", "reason_text",
                     "adjusted_by_username")
    date_hierarchy = "adjusted_at"


@admin.register(ArchiveEventLog)
class ArchiveEventLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("archive_year", "archive_month", "event_type", "level",
                    "operator_login", "original_timestamp")
    list_filter = ("archive_year", "archive_month", "event_type", "level")
    search_fields = ("operator_login", "message")
    date_hierarchy = "original_timestamp"
