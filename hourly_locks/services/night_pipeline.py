"""
Nochnoy konveyer dlya smeny 20-08 + kompensatsiya.

IDEMPOTENT: snachala rollback ranee verified, zatem zanovo.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils.timezone import now

from hourly_locks.models import (
    Compensation,
    Operator,
    Shift,
    WorkDebt,
    WorkDebtDetail,
    WorkLogDaily,
)

from . import external_api
from .cycle import get_or_create_active_cycle
from .event_log import log_event

logger = logging.getLogger(__name__)

NIGHT_NORM_FULL = timedelta(hours=12)
NIGHT_NORM_LOCK = timedelta(hours=2, minutes=20)


def run_night_pipeline(planned_date):
    """
    Zapuskaet nochnoy konveyer dlya vsekh 20-08 + comp zayavok.
    IDEMPOTENT: snachala otkat, zatem zanovo.
    """
    cycle = get_or_create_active_cycle()

    # 1. Otkat ranee verified night kompensatsiy
    rolled_back = rollback_night_compensations_for_date(planned_date)
    if rolled_back:
        logger.info("[night_pipeline] Otkacheno %d night-comp", rolled_back)

    # 2. Tekushaya proverka
    plans = Compensation.objects.filter(
        planned_date=planned_date,
        status="pending",
    ).filter(
        type_rule__verification_strategy="night_pipeline",
    ).select_related("operator", "type_rule")

    if not plans.exists():
        return {"processed": 0, "rolled_back": rolled_back}

    log_event(
        event_type="night_pipeline_run",
        level="info",
        message="Zapusk nochnogo konveyera za " + str(planned_date),
        cycle=cycle,
    )

    stats = {"approved": 0, "partial": 0, "declined": 0, "rolled_back": rolled_back}
    for plan in plans:
        try:
            log = _load_night_aggregate(plan.operator, planned_date, cycle)
            result = _verify_night_compensation(plan, log, cycle)
            stats[result] = stats.get(result, 0) + 1
        except Exception as exc:
            logger.exception("[night_pipeline] Oshibka dlya %s: %s", plan, exc)
            stats["errors"] = stats.get("errors", 0) + 1

    # Pipeline oxirida — WorkDebt'larni qayta hisoblash
    from .work_debt import recompute_for_date
    stats["recomputed"] = recompute_for_date(planned_date)

    return stats


def _load_night_aggregate(operator, planned_date, cycle):
    """
    Zagruzhaet dannye za:
      - noch (20:00 planned_date -> 08:00 next_date) = 12 ch smeny
      - utro (09:00-17:00 next_date) = dobavochnoe vremya
    Idempotent: WorkLogDaily.update_or_create.
    """
    next_date = planned_date + timedelta(days=1)

    night_rows_1 = external_api.fetch_hours_range(planned_date, range(20, 24))
    night_rows_2 = external_api.fetch_hours_range(next_date, range(0, 8))
    morning_rows = external_api.fetch_hours_range(next_date, range(8, 17))

    sums = {
        "aftercall_duration": timedelta(),
        "busy_duration": timedelta(),
        "hold_duration": timedelta(),
        "idle_duration": timedelta(),
        "lazy_duration": timedelta(),
        "lock_duration": timedelta(),
        "relax_duration": timedelta(),
        "full_duration": timedelta(),
    }

    for source in (night_rows_1, night_rows_2, morning_rows):
        for rows in source.values():
            delta = external_api.sum_for_login(rows, operator.login_id)
            for key, value in delta.items():
                sums[key] += value

    shift_obj = Shift.objects.filter(code="20-08").first()

    with transaction.atomic():
        log, _ = WorkLogDaily.objects.update_or_create(
            operator=operator,
            day=planned_date,
            defaults={
                "cycle": cycle,
                "shift": shift_obj,
                "shift_code_snapshot": "20-08",
                "start_at": datetime.combine(
                    planned_date, datetime.min.time().replace(hour=20),
                ),
                "end_at": datetime.combine(
                    next_date, datetime.min.time().replace(hour=17),
                ),
                "is_special_aggregation": True,
                **sums,
            },
        )

    logger.info("[night_pipeline] Agregat dlya %s: full=%s lock=%s",
                operator, log.full_duration, log.lock_duration)
    return log


def _verify_night_compensation(compensation, log, cycle):
    """
    Proveryaet kompensatsiyu po nochnoy smene 20-08.
      effective_overtime = max(fact_full - NORM_FULL, 0)
    """
    fact_full = log.full_duration or timedelta()
    fact_lock = log.lock_duration or timedelta()

    overtime = max(fact_full - NIGHT_NORM_FULL, timedelta(0))
    plan = compensation.requested_duration

    if overtime >= plan:
        status = "approved"
        credit = plan
        remaining = timedelta(0)
    elif overtime > timedelta(0):
        status = "partial"
        credit = overtime
        remaining = plan - credit
    else:
        status = "declined"
        credit = timedelta(0)
        remaining = plan

    note = (
        "Nochnaya smena 20-08 + kompensatsiya\n"
        "Otrabotano: {} (pereryv {})\n"
        "Pererabotka svyshe normy: {}\n"
        "Plan: {}\n"
        "Zachteno: {}\n"
        "Ostalos: {}\n"
        "Status: {}".format(fact_full, fact_lock, overtime, plan, credit, remaining, status)
    )

    with transaction.atomic():
        compensation.verified_duration = credit
        compensation.remaining_debt = remaining
        compensation.status = status
        compensation.verified_at = now()
        compensation.save(update_fields=[
            "verified_duration", "remaining_debt", "status",
            "verified_at", "updated_at",
        ])

        if status == "partial" and remaining > timedelta(0):
            # Shortfall WDD — informatsion. WorkDebt'ga qo'shilmaydi
            # (2x sanashning oldini olish).
            WorkDebtDetail.objects.update_or_create(
                operator=compensation.operator,
                day=compensation.planned_date,
                source="nb_compensation_shortfall",
                source_object_id=compensation.id,
                defaults={
                    "cycle": cycle,
                    "shift": log.shift,
                    "shift_code_snapshot": "20-08",
                    "violation_type": "insufficient_wh",
                    "norm_full": NIGHT_NORM_FULL,
                    "fact_full": credit,
                    "debt_full": remaining,
                    "norm_lock": NIGHT_NORM_LOCK,
                    "fact_lock": fact_lock,
                    "debt_lock": timedelta(0),
                    "note": note,
                    "locked_for_compensation": True,
                },
            )

    return status


# =============================================================================
# ROLLBACK
# =============================================================================

def rollback_night_compensations_for_date(planned_date):
    """
    Otmenyaet effekty ranee verified night-compensation na etoy date.
    """
    verified = Compensation.objects.filter(
        planned_date=planned_date,
        type_rule__verification_strategy="night_pipeline",
    ).exclude(status="pending").select_related("operator", "cycle")

    count = 0
    for comp in verified:
        try:
            _rollback_single_night(comp)
            count += 1
        except Exception as exc:
            logger.exception("[rollback_night] Oshibka dlya Comp#%d: %s", comp.id, exc)
    return count


@transaction.atomic
def _rollback_single_night(comp):
    """
    Otkat odnoy night compensation.
    QOIDA: WorkDebt'ga tegmaymiz — oxirida recompute chaqiriladi.
    """
    operator = comp.operator
    cycle = comp.cycle

    # 1. Shortfall WDD o'chiriladi
    WorkDebtDetail.objects.filter(
        operator=operator,
        source="nb_compensation_shortfall",
        source_object_id=comp.id,
    ).delete()

    # 2. Sbros kompensatsii
    comp.status = "pending"
    comp.verified_duration = None
    comp.remaining_debt = None
    comp.verified_at = None
    comp.deducted = False
    comp.save(update_fields=[
        "status", "verified_duration", "remaining_debt",
        "verified_at", "deducted", "updated_at",
    ])

    # 3. WorkDebt'ni qayta hisoblash
    from .work_debt import recompute_for_operator
    recompute_for_operator(operator, cycle)
