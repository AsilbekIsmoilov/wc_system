"""
Расчёт долгов операторов на основе ежедневных логов.

Алгоритм:
  1. Получаем WorkLogDaily для оператора за день.
  2. По смене получаем нормы (norm_full, norm_lock, tolerance).
  3. Считаем недоработку и превышение перерыва.
  4. Учитываем компенсирующую переработку.
  5. Создаём WorkDebtDetail и обновляем WorkDebt.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Optional

from django.db import transaction

from hourly_locks.models import (
    Compensation,
    Operator,
    OperatorScheduleDay,
    RequestTypeRule,
    Shift,
    Transfer,
    WorkDebt,
    WorkDebtDetail,
    WorkLogDaily,
)

from .automation_override import get_skipped_operator_ids
from .cycle import get_or_create_active_cycle
from .event_log import log_event

logger = logging.getLogger(__name__)


# =============================================================================
# Проверка одного лога (бывший check_debt)
# =============================================================================

def check_debt_for_log(log: WorkLogDaily) -> Dict:
    """
    Проверяет один WorkLogDaily на наличие долга по правилам смены.

    Возвращает dict с:
      - violation_type
      - debt_full, debt_lock
      - norm_full, norm_lock
      - make_up_wh (компенсирующая переработка)
      - note (текстовое описание)
    """
    shift = log.shift
    full = log.full_duration or timedelta()
    lock = log.lock_duration or timedelta()

    if not shift:
        return _empty_result(note=f"Неизвестная смена для {log.day}")

    norm_full = shift.norm_full
    norm_lock = shift.norm_lock_soft_cap
    tolerance = shift.tolerance_undertime

    result = {
        "debt_full": timedelta(),
        "debt_lock": timedelta(),
        "norm_full": norm_full,
        "norm_lock": norm_lock,
        "violation_type": None,
        "make_up_wh": timedelta(),
        "note": None,
    }

    notes = []
    has_insufficient_wh = False
    has_exceeding_break = False

    # ----- Проверка недоработки -----
    if tolerance > timedelta(0):
        if full + tolerance < norm_full:
            df = norm_full - full
            result["debt_full"] = df
            has_insufficient_wh = True
            notes.append(
                f"Недоработка (учёт допуска {tolerance}): {df} "
                f"(факт={full}, норма={norm_full})"
            )
        else:
            notes.append(
                f"Недоработка в пределах допуска {tolerance} "
                f"(факт={full}, норма={norm_full}) — без долга"
            )
    else:
        if full < norm_full:
            df = norm_full - full
            result["debt_full"] = df
            has_insufficient_wh = True
            notes.append(f"Недоработка: {df} (факт={full})")

    # ----- Проверка перерыва -----
    if lock > norm_lock:
        extra_break = lock - norm_lock
        extra_full_pos = max(full - norm_full, timedelta(0))
        result["make_up_wh"] = extra_full_pos

        # Для 9-часовых смен используется warn_at (например 1:30)
        warn_at = shift.norm_lock_warn_at
        is_9h_logic = warn_at > timedelta(0)

        if is_9h_logic:
            if lock > warn_at:
                effective_overbreak = (lock - warn_at) - extra_full_pos
                if effective_overbreak < timedelta(0):
                    effective_overbreak = timedelta(0)

                if effective_overbreak > timedelta(0):
                    result["debt_lock"] = effective_overbreak
                    has_exceeding_break = True
                    notes.append(
                        f"Перерыв превышен: lock={lock} (штраф от {warn_at}), "
                        f"допуск {norm_lock}, переработка={extra_full_pos}, "
                        f"остаток={effective_overbreak} (в долг)"
                    )
                else:
                    notes.append(
                        f"Перерыв превышен: lock={lock}, "
                        f"но компенсирован переработкой {extra_full_pos} — без долга"
                    )
            else:
                notes.append(f"Перерыв ≤ {warn_at} — в норме (lock={lock})")
        else:
            effective_overbreak = extra_break - extra_full_pos
            if effective_overbreak < timedelta(0):
                effective_overbreak = timedelta(0)

            if effective_overbreak > timedelta(0):
                result["debt_lock"] = effective_overbreak
                has_exceeding_break = True
                notes.append(
                    f"Перерыв превышен: lock={lock} > {norm_lock} (+{extra_break}), "
                    f"переработка={extra_full_pos}, остаток={effective_overbreak} (в долг)"
                )
            else:
                notes.append(
                    f"Перерыв превышен на {extra_break}, "
                    f"но компенсирован переработкой {extra_full_pos} — без долга"
                )

    # ----- Тип нарушения -----
    if has_insufficient_wh and has_exceeding_break:
        result["violation_type"] = "both_violations"
    elif has_insufficient_wh:
        result["violation_type"] = "insufficient_wh"
    elif has_exceeding_break:
        result["violation_type"] = "exceeding_break"

    result["note"] = " | ".join(notes) if notes else None
    return result


def _empty_result(note: str = "") -> Dict:
    return {
        "debt_full": timedelta(),
        "debt_lock": timedelta(),
        "norm_full": timedelta(),
        "norm_lock": timedelta(),
        "violation_type": None,
        "make_up_wh": timedelta(),
        "note": note,
    }


# =============================================================================
# Пакетный расчёт долгов за день
# =============================================================================

def calculate_work_debts(for_date: date) -> dict:
    """
    Считает долги для всех операторов за указанный день.

    Логика:
      1. Пропускаем операторов с AutomationOverride='skip_debt_calc'.
      2. Пропускаем операторов с активным Transfer типа, освобождающего от долга
         (RequestTypeRule.exempts_from_daily_debt=True).
      3. Пропускаем 20-08 с компенсацией (обрабатывается ночным конвейером).
      4. Для остальных — check_debt_for_log → создание WorkDebtDetail.
    """
    cycle = get_or_create_active_cycle()

    if not cycle.contains(for_date):
        logger.info("[debt_calc] %s вне активного цикла, пропуск", for_date)
        return {"status": "skipped", "reason": "date_outside_cycle"}

    logger.info("[debt_calc] Старт расчёта за %s", for_date)

    # Операторы с переопределением — пропускаем
    skipped_override_ids = get_skipped_operator_ids("skip_debt_calc", for_date)

    # Операторы с активными Transfer'ами, освобождающими от долга
    exempt_rules = RequestTypeRule.objects.filter(
        category="transfer",
        exempts_from_daily_debt=True,
        is_active=True,
    )

    exempt_qs = Transfer.objects.filter(
        type_rule__in=exempt_rules,
        status__in=["pending", "in_progress", "approved"],
        date_from__lte=for_date,
        date_to__gte=for_date,
    ).select_related("type_rule")

    exempt_full_ids = set()  # operator_id, полностью освобождённые
    exempt_partial = {}  # operator_id → {"duration": ..., "type_code": ...}

    for transfer in exempt_qs:
        rule = transfer.type_rule
        op_id = transfer.operator_id

        # Если есть длительность — частичное освобождение (например, time_off)
        if transfer.requested_duration and transfer.requested_duration > timedelta(0):
            exempt_partial[op_id] = {
                "duration": transfer.requested_duration,
                "type_code": rule.code,
            }
        else:
            exempt_full_ids.add(op_id)

    # Переносы (тип transfer) — на date_from пропускаем
    transfer_rule_codes = ["transfer"]
    transfer_ops_today = set(
        Transfer.objects.filter(
            type_rule__code__in=transfer_rule_codes,
            status__in=["pending", "in_progress"],
            date_from=for_date,
        ).values_list("operator_id", flat=True)
    )

    # 20-08 с компенсацией
    special_pipeline_ids = set(
        OperatorScheduleDay.objects.filter(
            day=for_date,
            shift__requires_special_pipeline=True,
        )
        .filter(
            operator_id__in=Compensation.objects.filter(
                planned_date=for_date,
                status__in=["pending", "approved", "partial"],
            ).values_list("operator_id", flat=True)
        )
        .values_list("operator_id", flat=True)
    )

    # Основной цикл
    logs = WorkLogDaily.objects.filter(day=for_date).select_related(
        "operator", "shift",
    )
    stats = {"created": 0, "skipped": 0}

    with transaction.atomic():
        for log in logs:
            operator = log.operator
            op_id = operator.id

            if op_id in skipped_override_ids:
                stats["skipped"] += 1
                continue

            if op_id in special_pipeline_ids:
                logger.info(
                    "[debt_calc] SKIP %s (20-08 + comp → ночной конвейер)",
                    operator,
                )
                stats["skipped"] += 1
                continue

            if op_id in exempt_full_ids:
                stats["skipped"] += 1
                continue

            if op_id in transfer_ops_today:
                stats["skipped"] += 1
                continue

            # Частичное освобождение
            if op_id in exempt_partial:
                _handle_partial_exempt(
                    log=log,
                    operator=operator,
                    cycle=cycle,
                    skip_info=exempt_partial[op_id],
                )
                stats["created"] += 1
                continue

            # Обычный расчёт
            _create_debt_record(log, operator, cycle)
            stats["created"] += 1

    # WorkDebt'larni qayta hisoblash (single source of truth)
    from .work_debt import recompute_for_date
    recompute_stats = recompute_for_date(for_date)
    stats["recomputed"] = recompute_stats

    log_event(
        event_type="debt_calculated",
        level="info",
        message=f"Расчёт долгов за {for_date}: {stats}",
        cycle=cycle,
        payload=stats,
    )

    logger.info("[debt_calc] Завершено за %s: %s", for_date, stats)
    return stats


def _create_debt_record(log: WorkLogDaily, operator: Operator, cycle):
    """
    Создаёт WorkDebtDetail.

    QOIDA: WorkDebt'ga to'g'ridan-to'g'ri tegmaymiz —
    `services.work_debt.recompute_for_operator` orqali hisoblanadi.

    Idempotency: locked WDD bo'lsa tegmaymiz.
    """
    # 0. Tekshirish: locked WDD bormi? Bor bo'lsa tegmaymiz (idempotency)
    locked_exists = WorkDebtDetail.objects.filter(
        operator=operator,
        day=log.day,
        source="shift",
        shift=log.shift,
        locked_for_compensation=True,
    ).exists()
    if locked_exists:
        logger.info(
            "[debt_calc] SKIP %s %s — WDD allaqachon kompensatsiyaga bog'langan",
            operator, log.day,
        )
        return

    # 1. Eski yozuvlarni o'chiramiz (locked emas)
    WorkDebtDetail.objects.filter(
        operator=operator,
        day=log.day,
        source="shift",
        shift=log.shift,
    ).delete()

    # 2. Yangi qarz hisoblash
    result = check_debt_for_log(log)
    debt_value = result["debt_full"] + result["debt_lock"]

    if debt_value <= timedelta(0):
        return

    WorkDebtDetail.objects.create(
        operator=operator,
        day=log.day,
        cycle=cycle,
        source="shift",
        shift=log.shift,
        shift_code_snapshot=log.shift.code if log.shift else None,
        violation_type=result["violation_type"],
        norm_full=result["norm_full"],
        fact_full=log.full_duration,
        debt_full=result["debt_full"],
        norm_lock=result["norm_lock"],
        fact_lock=log.lock_duration,
        debt_lock=result["debt_lock"],
        make_up_wh=result["make_up_wh"],
        note=result["note"],
    )


def _handle_partial_exempt(
    log: WorkLogDaily,
    operator: Operator,
    cycle,
    skip_info: dict,
):
    """
    Qisman ozod qilingan operatorning kunlik WDD'sini yangilaydi.

    QOIDA: WorkDebt'ga tegmaymiz — recompute orqali hisoblanadi.
    """
    skip_duration = skip_info["duration"]
    type_code = skip_info["type_code"]

    # LOCKED tekshirish
    locked_exists = WorkDebtDetail.objects.filter(
        operator=operator, day=log.day, source="shift",
        locked_for_compensation=True,
    ).exists()
    if locked_exists:
        logger.info(
            "[debt_calc partial] SKIP %s %s — WDD locked",
            operator, log.day,
        )
        return

    result = check_debt_for_log(log)
    day_total_debt = result["debt_full"] + result["debt_lock"]

    remaining_debt = day_total_debt - skip_duration
    if remaining_debt < timedelta(0):
        remaining_debt = timedelta(0)

    note = (
        f"Частичное освобождение ({type_code}): длительность {skip_duration}, "
        f"факт={log.full_duration}, перерыв={log.lock_duration}, "
        f"дневной долг={day_total_debt}, остаток={remaining_debt}"
    )

    WorkDebtDetail.objects.update_or_create(
        operator=operator,
        day=log.day,
        source="shift",
        defaults={
            "cycle": cycle,
            "shift": log.shift,
            "shift_code_snapshot": log.shift.code if log.shift else None,
            "violation_type": result["violation_type"],
            "norm_full": result["norm_full"],
            "fact_full": log.full_duration or timedelta(),
            "debt_full": remaining_debt,
            "norm_lock": result["norm_lock"],
            "fact_lock": log.lock_duration or timedelta(),
            "debt_lock": timedelta(0),
            "make_up_wh": result["make_up_wh"],
            "note": note,
        },
    )
