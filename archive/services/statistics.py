"""
Sbor statistiki za zakrytyy tsikl.

Zameshchaet staryy archive_statistics.py s raw SQL na chistyy ORM.
"""

from datetime import timedelta
from typing import List, Optional

from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from archive.models import (
    ArchiveCompensation,
    ArchiveCycle,
    ArchiveOperatorSnapshot,
    ArchiveTransfer,
    ArchiveWorkDebt,
)
from archive.services.scope import get_visible_operator_ids


def format_duration(value: Optional[timedelta]) -> str:
    """Vremya v format HH:MM:SS."""
    if not value or value.total_seconds() <= 0:
        return "00:00:00"
    total_seconds = int(value.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class StatisticsService:
    """
    Glavnyy servis statistiki.

    Ispolzovanie:
      service = StatisticsService(year=2026, month=5, user=request.user)
      data = service.collect()
    """

    # Tipy zayavok dlya kategoriy
    WORK_TYPES = {"compensation", "nb_compensation"}
    EXCLUSION_TYPES = {
        "sl", "wc", "study", "vacation", "exception",
        "training", "office_work", "benefits", "partial_exception",
    }
    REJECTION_TYPES = {"no_compensation"}

    def __init__(self, year: int, month: int, user, group_id: Optional[int] = None):
        self.year = year
        self.month = month
        self.user = user
        self.group_id = group_id

        # Operatorlar koto'rini polzovatel vidit
        self.operator_ids = get_visible_operator_ids(user, year, month) or []

        # Esli zayavlena gruppa — filtruem
        if group_id:
            self.operator_ids = self._filter_by_group(self.operator_ids, group_id)

        self.base_filter = {
            "archive_year": year,
            "archive_month": month,
            "operator_id__in": self.operator_ids,
        }

    def _filter_by_group(self, op_ids: List[int], group_id: int) -> List[int]:
        """Ostavlyaem tolko operatorov iz konkretnoy gruppy."""
        return list(
            ArchiveOperatorSnapshot.objects
            .using("archive")
            .filter(
                archive_year=self.year,
                archive_month=self.month,
                operator_id__in=op_ids,
                group_id=group_id,
            )
            .values_list("operator_id", flat=True)
        )

    def _cycle(self):
        """Cycle za year/month."""
        try:
            return ArchiveCycle.objects.using("archive").get(
                year=self.year, month=self.month,
            )
        except ArchiveCycle.DoesNotExist:
            return None

    # =========================================================================
    # Otdelnye metriki
    # =========================================================================

    def _total_operators(self) -> int:
        return len(self.operator_ids)

    def _total_records(self) -> int:
        comp_count = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
        ).count()
        tr_count = ArchiveTransfer.objects.using("archive").filter(
            **self.base_filter,
        ).count()
        return comp_count + tr_count

    def _total_debt(self) -> dict:
        """Itogovyy dolg po operatoram za tsikl."""
        if not self.operator_ids:
            return {"duration": "00:00:00", "count": 0}

        qs = ArchiveWorkDebt.objects.using("archive").filter(**self.base_filter)
        agg = qs.aggregate(
            total=Coalesce(Sum("final_debt"), timedelta(0)),
            count=Count("id"),
        )
        return {
            "duration": format_duration(agg["total"]),
            "count": agg["count"],
        }

    def _worked(self) -> dict:
        """Otrabotannye kompensatsii (approved compensation/nb_compensation)."""
        qs = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.WORK_TYPES),
            status="approved",
        )
        agg = qs.aggregate(
            total=Coalesce(Sum("requested_duration"), timedelta(0)),
            count=Count("id"),
        )
        return {
            "duration": format_duration(agg["total"]),
            "count": agg["count"],
        }

    def _partial_worked(self) -> dict:
        """Chastichno otrabotannye."""
        qs = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.WORK_TYPES),
            status="partial",
        )
        agg = qs.aggregate(
            total=Coalesce(Sum("verified_duration"), timedelta(0)),
            count=Count("id"),
        )
        return {
            "duration": format_duration(agg["total"]),
            "count": agg["count"],
        }

    def _not_worked(self) -> dict:
        """Ne otrabotannye (declined)."""
        qs = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.WORK_TYPES),
            status="declined",
        )
        agg = qs.aggregate(
            total=Coalesce(Sum("requested_duration"), timedelta(0)),
            count=Count("id"),
        )
        return {
            "duration": format_duration(agg["total"]),
            "count": agg["count"],
        }

    def _rejected_by_operator(self) -> dict:
        """Otkazy operatora otrabotat (no_compensation, approved)."""
        qs = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.REJECTION_TYPES),
            status="approved",
        )
        agg = qs.aggregate(
            total=Coalesce(Sum("requested_duration"), timedelta(0)),
            count=Count("id"),
        )
        return {
            "duration": format_duration(agg["total"]),
            "count": agg["count"],
        }

    def _excluded(self) -> dict:
        """Vse iskliyuchenia: sl, vacation, training i t.p."""
        comp_qs = ArchiveCompensation.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.EXCLUSION_TYPES),
            status="approved",
        )
        comp_agg = comp_qs.aggregate(
            total=Coalesce(Sum("requested_duration"), timedelta(0)),
            count=Count("id"),
        )
        tr_qs = ArchiveTransfer.objects.using("archive").filter(
            **self.base_filter,
            type_code__in=list(self.EXCLUSION_TYPES),
            status__in=["completed", "approved"],
        )
        tr_agg = tr_qs.aggregate(
            total=Coalesce(Sum("requested_duration"), timedelta(0)),
            count=Count("id"),
        )
        total = (comp_agg["total"] or timedelta(0)) + (tr_agg["total"] or timedelta(0))
        count = comp_agg["count"] + tr_agg["count"]
        return {
            "duration": format_duration(total),
            "count": count,
        }

    def _types_summary(self) -> dict:
        """Razbivka po vsem tipam: {sl: {count, duration}, vacation: {...}, ...}"""
        result = {}

        type_list = list(self.EXCLUSION_TYPES) + list(self.WORK_TYPES) + list(self.REJECTION_TYPES) + ["transfer", "time_off"]

        for type_code in type_list:
            # Compensation
            comp = ArchiveCompensation.objects.using("archive").filter(
                **self.base_filter,
                type_code=type_code,
                status__in=["approved", "completed"],
            ).aggregate(
                total=Coalesce(Sum("requested_duration"), timedelta(0)),
                count=Count("id"),
            )
            # Transfer
            tr = ArchiveTransfer.objects.using("archive").filter(
                **self.base_filter,
                type_code=type_code,
                status__in=["approved", "completed"],
            ).aggregate(
                total=Coalesce(Sum("requested_duration"), timedelta(0)),
                count=Count("id"),
            )

            duration = (comp["total"] or timedelta(0)) + (tr["total"] or timedelta(0))
            count = comp["count"] + tr["count"]

            if count > 0:
                result[type_code] = {
                    "duration": format_duration(duration),
                    "count": count,
                }

        return result

    def _operators_table(self) -> list:
        """Tablitsa po operatoram: kazhdaya stroka — odin operator."""
        operators_qs = ArchiveOperatorSnapshot.objects.using("archive").filter(
            archive_year=self.year,
            archive_month=self.month,
            operator_id__in=self.operator_ids,
        )

        rows = []
        for op in operators_qs:
            # Worked
            worked = ArchiveCompensation.objects.using("archive").filter(
                archive_year=self.year, archive_month=self.month,
                operator_id=op.operator_id,
                type_code__in=list(self.WORK_TYPES),
                status="approved",
            ).aggregate(
                total=Coalesce(Sum("requested_duration"), timedelta(0)),
            )["total"]

            # Final debt
            debt_qs = ArchiveWorkDebt.objects.using("archive").filter(
                archive_year=self.year, archive_month=self.month,
                operator_id=op.operator_id,
            ).first()
            final_debt = debt_qs.final_debt if debt_qs else timedelta(0)

            rows.append({
                "operator_id": op.operator_id,
                "login_id": op.operator_login,
                "fio": op.fio,
                "group": op.group_name,
                "worked": format_duration(worked),
                "final_debt": format_duration(final_debt),
            })

        return rows

    # =========================================================================
    # Glavnyy metod
    # =========================================================================

    def collect(self) -> dict:
        """Sobiraet vsyu statistiku v odin dict s keshirovaniem."""
        cache_key = (
            f"archive_stats:user:{self.user.id}:"
            f"year:{self.year}:month:{self.month}:"
            f"group:{self.group_id or 'all'}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        if not self.operator_ids:
            data = {
                "cycle": None,
                "total_operators": 0,
                "total_records": 0,
                "total_debt": {"duration": "00:00:00", "count": 0},
                "worked": {"duration": "00:00:00", "count": 0},
                "partial_worked": {"duration": "00:00:00", "count": 0},
                "not_worked": {"duration": "00:00:00", "count": 0},
                "rejected_by_operator": {"duration": "00:00:00", "count": 0},
                "excluded": {"duration": "00:00:00", "count": 0},
                "types_summary": {},
                "operators_table": [],
            }
            cache.set(cache_key, data, timeout=300)
            return data

        cycle = self._cycle()
        data = {
            "cycle": {
                "year": cycle.year, "month": cycle.month,
                "start_date": str(cycle.start_date) if cycle else None,
                "end_date": str(cycle.end_date) if cycle else None,
            } if cycle else None,
            "total_operators": self._total_operators(),
            "total_records": self._total_records(),
            "total_debt": self._total_debt(),
            "worked": self._worked(),
            "partial_worked": self._partial_worked(),
            "not_worked": self._not_worked(),
            "rejected_by_operator": self._rejected_by_operator(),
            "excluded": self._excluded(),
            "types_summary": self._types_summary(),
            "operators_table": self._operators_table(),
        }

        cache.set(cache_key, data, timeout=300)
        return data
