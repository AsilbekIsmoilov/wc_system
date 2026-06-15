"""
WorkDebt — derived/cached qiymat (single source of truth).

Manba:
  - WorkDebtDetail (shortfall'lardan tashqari) — jami qarz
  - CompensationDebtLink (applied=True) — qoplangan kredit

Hisob:
  total_accumulated = sum(WDD.debt) [shortfall'lardan tashqari]
  current_debt      = max(total_accumulated - sum(applied_credit), 0)
"""

import logging
from datetime import timedelta
from typing import Iterable

from django.db import transaction

from hourly_locks.models import (
    CompensationDebtLink,
    Operator,
    WorkDebt,
    WorkDebtDetail,
)

logger = logging.getLogger(__name__)

SHORTFALL_SOURCES = {"compensation_shortfall", "nb_compensation_shortfall"}


def recompute_for_operator(operator, cycle) -> tuple:
    total_accum = timedelta(0)
    for wdd in WorkDebtDetail.objects.filter(
        operator=operator, cycle=cycle,
    ).exclude(source__in=SHORTFALL_SOURCES):
        total_accum += (wdd.debt_full or timedelta(0)) + (wdd.debt_lock or timedelta(0))

    total_applied = timedelta(0)
    for link in CompensationDebtLink.objects.filter(
        compensation__operator=operator,
        compensation__cycle=cycle,
        applied=True,
    ):
        total_applied += link.applied_amount or timedelta(0)

    new_current = max(total_accum - total_applied, timedelta(0))

    with transaction.atomic():
        wd, _ = WorkDebt.objects.select_for_update().get_or_create(
            operator=operator, cycle=cycle,
        )
        changed = (
            wd.current_debt != new_current
            or wd.total_accumulated != total_accum
        )
        if changed:
            wd.current_debt = new_current
            wd.total_accumulated = total_accum
            wd.save(update_fields=["current_debt", "total_accumulated", "updated_at"])

    return new_current, total_accum, changed


def recompute_for_operators(operator_ids: Iterable[int], cycle) -> dict:
    operator_ids = list(set(operator_ids))
    if not operator_ids:
        return {"recomputed": 0, "changed": 0}

    operators = Operator.objects.filter(id__in=operator_ids)
    changed_count = 0
    for op in operators:
        _, _, changed = recompute_for_operator(op, cycle)
        if changed:
            changed_count += 1

    logger.info(
        "[work_debt] Recomputed %d operators (cycle=%s), %d changed",
        len(operator_ids), cycle, changed_count,
    )
    return {"recomputed": len(operator_ids), "changed": changed_count}


def recompute_for_cycle(cycle) -> dict:
    op_ids_wdd = set(WorkDebtDetail.objects.filter(
        cycle=cycle,
    ).values_list("operator_id", flat=True))

    op_ids_wd = set(WorkDebt.objects.filter(
        cycle=cycle,
    ).values_list("operator_id", flat=True))

    op_ids = op_ids_wdd | op_ids_wd
    return recompute_for_operators(op_ids, cycle)


def recompute_all() -> dict:
    total_recomputed = 0
    total_changed = 0

    from hourly_locks.models import Cycle
    for cycle in Cycle.objects.all():
        result = recompute_for_cycle(cycle)
        total_recomputed += result["recomputed"]
        total_changed += result["changed"]

    logger.info(
        "[work_debt] recompute_all: total=%d, changed=%d",
        total_recomputed, total_changed,
    )
    return {"recomputed": total_recomputed, "changed": total_changed}


def recompute_for_date(for_date) -> dict:
    from .cycle import get_or_create_active_cycle, get_cycle_for_date

    cycle = get_cycle_for_date(for_date) or get_or_create_active_cycle()

    op_ids = set(WorkDebtDetail.objects.filter(
        day=for_date,
    ).values_list("operator_id", flat=True))

    return recompute_for_operators(op_ids, cycle)
