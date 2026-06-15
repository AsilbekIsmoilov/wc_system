from datetime import date
from typing import Optional, Set

from django.db.models import Q

from hourly_locks.models import AutomationOverride


def has_override(
    operator,
    override_type: str,
    on_date: Optional[date] = None,
) -> bool:
    if on_date is None:
        on_date = date.today()

    return AutomationOverride.objects.filter(
        operator=operator,
        override_type=override_type,
        is_active=True,
        valid_from__lte=on_date,
    ).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    ).exists()


def get_skipped_operator_ids(
    override_type: str,
    on_date: Optional[date] = None,
) -> Set[int]:
    if on_date is None:
        on_date = date.today()

    qs = AutomationOverride.objects.filter(
        override_type=override_type,
        is_active=True,
        valid_from__lte=on_date,
    ).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    )

    return set(qs.values_list("operator_id", flat=True))