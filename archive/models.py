from datetime import timedelta

from django.db import models


class ArchiveCycle(models.Model):
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField()
    closed_by_id = models.PositiveIntegerField(null=True, blank=True)
    closed_by_username = models.CharField(max_length=150, blank=True, null=True)

    archive_stats = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        unique_together = ("year", "month")
        indexes = [
            models.Index(fields=["year", "month"]),
            models.Index(fields=["end_date"]),
        ]
        ordering = ["-year", "-month"]

    def __str__(self):
        return "Arkhiv tsikl {}/{:02d} ({}-{})".format(
            self.year, self.month, self.start_date, self.end_date,
        )


class ArchiveOperatorSnapshot(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    surname = models.CharField(max_length=150)
    name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True, null=True)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        unique_together = ("archive_year", "archive_month", "operator_id")
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id"]),
            models.Index(fields=["operator_login"]),
        ]

    @property
    def fio(self):
        return "{} {} {}".format(self.surname, self.name, self.middle_name or "").strip()


class ArchiveWorkLogDaily(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    operator_fio = models.CharField(max_length=400)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    day = models.DateField()
    shift_code = models.CharField(max_length=20, blank=True, null=True)

    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    aftercall_duration = models.DurationField(default=timedelta)
    busy_duration = models.DurationField(default=timedelta)
    hold_duration = models.DurationField(default=timedelta)
    idle_duration = models.DurationField(default=timedelta)
    lazy_duration = models.DurationField(default=timedelta)
    lock_duration = models.DurationField(default=timedelta)
    relax_duration = models.DurationField(default=timedelta)
    full_duration = models.DurationField(default=timedelta)

    is_special_aggregation = models.BooleanField(default=False)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id", "day"]),
            models.Index(fields=["day"]),
        ]


class ArchiveWorkDebt(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    operator_fio = models.CharField(max_length=400)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    final_debt = models.DurationField(default=timedelta(0))
    total_accumulated = models.DurationField(default=timedelta(0))

    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        unique_together = ("archive_year", "archive_month", "operator_id")
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id"]),
        ]


class ArchiveWorkDebtDetail(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    operator_fio = models.CharField(max_length=400)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    day = models.DateField()
    source = models.CharField(max_length=30, default="shift")
    source_object_id = models.PositiveIntegerField(null=True, blank=True)

    shift_code = models.CharField(max_length=20, blank=True, null=True)
    violation_type = models.CharField(max_length=30, blank=True, null=True)

    norm_full = models.DurationField(default=timedelta)
    fact_full = models.DurationField(default=timedelta)
    debt_full = models.DurationField(default=timedelta)
    norm_lock = models.DurationField(default=timedelta)
    fact_lock = models.DurationField(default=timedelta)
    debt_lock = models.DurationField(default=timedelta)

    make_up_wh = models.DurationField(default=timedelta)
    locked_for_compensation = models.BooleanField(default=False)

    note = models.TextField(blank=True, null=True)
    original_created_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id", "day"]),
            models.Index(fields=["source"]),
            models.Index(fields=["day"]),
        ]


class ArchiveCompensation(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    operator_fio = models.CharField(max_length=400)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    type_code = models.CharField(max_length=30)
    type_display = models.CharField(max_length=100)

    source = models.CharField(max_length=20, default="requested")

    status = models.CharField(max_length=20)
    planned_date = models.DateField()

    requested_duration = models.DurationField()
    verified_duration = models.DurationField(null=True, blank=True)
    remaining_debt = models.DurationField(null=True, blank=True)
    deducted = models.BooleanField(default=False)

    comment = models.TextField(blank=True, null=True)
    debts_snapshot = models.JSONField(default=list, blank=True)
    debt_links_snapshot = models.JSONField(default=list, blank=True)

    claim_metadata = models.JSONField(default=dict, blank=True)
    auto_check_result = models.JSONField(default=dict, blank=True)
    auto_check_at = models.DateTimeField(null=True, blank=True)

    pdf_file_path = models.CharField(max_length=500, blank=True, null=True)
    screens_path = models.CharField(max_length=500, blank=True, null=True)

    original_id = models.PositiveIntegerField()
    original_created_at = models.DateTimeField()
    original_updated_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    verified_by_id = models.PositiveIntegerField(null=True, blank=True)
    fixed_by_id = models.PositiveIntegerField(null=True, blank=True)

    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id", "planned_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["original_id"]),
            models.Index(fields=["source"]),
        ]


class ArchiveTransfer(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    operator_id = models.PositiveIntegerField()
    operator_login = models.CharField(max_length=50)
    operator_fio = models.CharField(max_length=400)

    group_id = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True, null=True)

    type_code = models.CharField(max_length=30)
    type_display = models.CharField(max_length=100)

    status = models.CharField(max_length=20)

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    hour_from = models.TimeField(null=True, blank=True)
    hour_to = models.TimeField(null=True, blank=True)

    requested_duration = models.DurationField(null=True, blank=True)
    verified_duration = models.DurationField(null=True, blank=True)
    remaining_debt = models.DurationField(null=True, blank=True)

    comment = models.TextField(blank=True, null=True)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    screens_path = models.CharField(max_length=500, blank=True, null=True)

    original_id = models.PositiveIntegerField()
    original_created_at = models.DateTimeField()
    original_updated_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    verified_by_id = models.PositiveIntegerField(null=True, blank=True)
    fixed_by_id = models.PositiveIntegerField(null=True, blank=True)

    was_split = models.BooleanField(default=False)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id", "date_from"]),
            models.Index(fields=["operator_id", "date_to"]),
            models.Index(fields=["type_code"]),
            models.Index(fields=["status"]),
            models.Index(fields=["original_id"]),
        ]


class ArchiveManualAdjustment(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    target_type = models.CharField(max_length=30)
    target_id = models.PositiveIntegerField()

    operator_id = models.PositiveIntegerField(null=True, blank=True)
    operator_login = models.CharField(max_length=50, blank=True, null=True)

    field_name = models.CharField(max_length=100)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField()

    reason_code = models.CharField(max_length=50)
    reason_text = models.TextField()

    adjusted_by_id = models.PositiveIntegerField()
    adjusted_by_username = models.CharField(max_length=150)
    adjusted_at = models.DateTimeField()

    approved_by_id = models.PositiveIntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    original_id = models.PositiveIntegerField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["operator_id"]),
            models.Index(fields=["adjusted_by_id"]),
            models.Index(fields=["target_type", "target_id"]),
        ]


class ArchiveEventLog(models.Model):
    archive_year = models.PositiveSmallIntegerField()
    archive_month = models.PositiveSmallIntegerField()

    event_type = models.CharField(max_length=50)
    level = models.CharField(max_length=20)

    operator_id = models.PositiveIntegerField(null=True, blank=True)
    operator_login = models.CharField(max_length=50, blank=True, null=True)

    target_type = models.CharField(max_length=30, blank=True, null=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)

    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    original_timestamp = models.DateTimeField()
    triggered_by_id = models.PositiveIntegerField(null=True, blank=True)

    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "archive"
        indexes = [
            models.Index(fields=["archive_year", "archive_month"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["level"]),
            models.Index(fields=["operator_id"]),
        ]
