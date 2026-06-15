"""
Ретроактивная проверка компенсации.

Сценарий: оператор фактически отработал лишнее, но не подал заявку заранее.
Постфактум он подаёт заявку, указывая дату. Система проверяет логи и
выдаёт предварительное решение. Финальное решение остаётся за супервайзером.
"""

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils.timezone import now

from hourly_locks.models import (
    Compensation,
    OperatorScheduleDay,
    WorkLogDaily,
)

from . import external_api
from .event_log import log_event

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = timedelta(minutes=5)


def auto_check_retroactive(
    compensation: Compensation,
    for_date: date,
    cycle,
) -> str:
    """
    Ретроактивная проверка: смотрит фактические данные и записывает
    результат в auto_check_result. Status остаётся pending — решает супервайзер.
    """
    operator = compensation.operator
    log = WorkLogDaily.objects.filter(operator=operator, day=for_date).first()

    schedule = OperatorScheduleDay.objects.filter(
        operator=operator, day=for_date,
    ).select_related("shift").first()

    fact_full = log.full_duration if log else timedelta(0)
    fact_lock = log.lock_duration if log else timedelta(0)

    # Если лога нет — пробуем загрузить с API напрямую
    if not log:
        day_data = external_api.fetch_hours_range(for_date, range(0, 24))
        for rows in day_data.values():
            delta = external_api.sum_for_login(rows, operator.login_id)
            fact_full += delta["full_duration"]
            fact_lock += delta["lock_duration"]

    # Transfer duration ni hisobga olamiz (compensation_verifier mantiqi bilan bir xil)
    from .compensation_verifier import _get_exempt_duration_for_day
    transfer_duration = _get_exempt_duration_for_day(operator, for_date)

    # Расчёт доступной переработки
    if schedule and schedule.shift:
        # WORKDAY: smena normasi Transfer.duration ga kamayadi
        shift = schedule.shift
        effective_norm_full = max(shift.norm_full - transfer_duration, timedelta(0))
        overtime = max(fact_full - effective_norm_full, timedelta(0))
        over_lock = max(fact_lock - shift.norm_lock_soft_cap, timedelta(0))
        available_credit = max(overtime - over_lock, timedelta(0))
        shift_info = {
            "shift_code": shift.code,
            "shift_norm_full": str(shift.norm_full),
            "shift_norm_lock": str(shift.norm_lock_soft_cap),
            "transfer_duration": str(transfer_duration),
            "effective_norm_full": str(effective_norm_full),
        }
    elif schedule and schedule.is_day_off:
        # DAY OFF: Variant A — Transfer to'la, qoldiq comp'ga
        net = max(fact_full - fact_lock, timedelta(0))
        available_credit = max(net - transfer_duration, timedelta(0))
        shift_info = {
            "shift_code": None, "is_day_off": True,
            "transfer_duration": str(transfer_duration),
        }
    else:
        # Расписания нет — Variant A
        net = max(fact_full - fact_lock, timedelta(0))
        available_credit = max(net - transfer_duration, timedelta(0))
        shift_info = {
            "shift_code": None, "no_schedule": True,
            "transfer_duration": str(transfer_duration),
        }

    # Определяем предварительный статус
    requested = compensation.requested_duration
    tolerance = DEFAULT_TOLERANCE

    if available_credit + tolerance >= requested:
        suggested_status = "approved"
        computed_credit = requested
    elif available_credit > timedelta(0):
        suggested_status = "partial"
        computed_credit = available_credit
    else:
        suggested_status = "declined"
        computed_credit = timedelta(0)

    # Записываем результат
    compensation.auto_check_result = {
        "fact_full": str(fact_full),
        "fact_lock": str(fact_lock),
        "available_credit": str(available_credit),
        "computed_credit": str(computed_credit),
        "suggested_status": suggested_status,
        "requested": str(requested),
        **shift_info,
    }
    compensation.auto_check_at = now()
    # Статус НЕ меняется — остаётся pending, ждёт супервайзера
    compensation.save(update_fields=[
        "auto_check_result", "auto_check_at", "updated_at",
    ])

    log_event(
        event_type="retroactive_check",
        level="info",
        operator=operator,
        cycle=cycle,
        target_type="compensation",
        target_id=compensation.id,
        message=(
            f"Ретроактивная проверка за {for_date}: "
            f"credit={computed_credit}, предложено={suggested_status}"
        ),
        payload=compensation.auto_check_result,
    )

    # Возвращаем "skipped" т.к. статус не финализирован
    return "skipped"
