"""
Управление циклами (Cycle).

Цикл — это период с 20-го числа предыдущего месяца по 19-е число текущего.
В default DB всегда существует ровно ОДИН активный цикл.

Основные функции:
  - get_active_cycle()       — текущий активный цикл
  - get_or_create_active()   — создаёт цикл, если его нет
  - calculate_bounds(ref)    — границы цикла для произвольной даты
  - close_cycle(cycle, user) — закрытие цикла (запуск архивации)
  - auto_close_if_due(today) — авто-закрытие 20-го числа
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Tuple

from django.db import transaction
from django.utils.timezone import now

from hourly_locks.models import Cycle

logger = logging.getLogger(__name__)


# =============================================================================
# Расчёт границ цикла (чистые функции)
# =============================================================================

def calculate_bounds(ref_date: date) -> Tuple[date, date]:
    """
    Возвращает (start_date, end_date) цикла, к которому относится ref_date.

    Примеры:
      ref_date = 2026-05-15 → (2026-04-20, 2026-05-19)
      ref_date = 2026-05-20 → (2026-05-20, 2026-06-19)
      ref_date = 2026-05-19 → (2026-04-20, 2026-05-19)
    """
    y, m, d = ref_date.year, ref_date.month, ref_date.day

    if d >= 20:
        start = date(y, m, 20)
        if m == 12:
            end = date(y + 1, 1, 19)
        else:
            end = date(y, m + 1, 19)
    else:
        if m == 1:
            start = date(y - 1, 12, 20)
        else:
            start = date(y, m - 1, 20)
        end = date(y, m, 19)

    return start, end


def calculate_year_month(end_date: date) -> Tuple[int, int]:
    """По дате окончания цикла возвращает (year, month) для нумерации."""
    return end_date.year, end_date.month


def calculate_previous_cycle_bounds(today: date) -> Tuple[date, date]:
    """
    Возвращает границы предыдущего (только что закрытого) цикла.
    Если today = 2026-05-20, то предыдущий цикл = (2026-04-20, 2026-05-19).
    """
    if today.day >= 20:
        return calculate_bounds(today.replace(day=19))

    if today.month == 1:
        prev_19 = date(today.year - 1, 12, 19)
    else:
        prev_19 = date(today.year, today.month - 1, 19)
    return calculate_bounds(prev_19)


# =============================================================================
# Получение и создание циклов
# =============================================================================

def get_active_cycle() -> Optional[Cycle]:
    """Возвращает текущий активный цикл (или None)."""
    return Cycle.objects.filter(status="active").first()


@transaction.atomic
def get_or_create_active_cycle(today: Optional[date] = None) -> Cycle:
    """
    Возвращает активный цикл; если его нет — создаёт по текущей дате.
    """
    if today is None:
        today = date.today()

    active = get_active_cycle()
    if active:
        return active

    start, end = calculate_bounds(today)
    year, month = calculate_year_month(end)

    cycle, created = Cycle.objects.get_or_create(
        year=year,
        month=month,
        defaults={
            "start_date": start,
            "end_date": end,
            "status": "active",
        },
    )

    if created:
        logger.info("Создан новый цикл: %s", cycle)
        from .event_log import log_event
        log_event(
            event_type="cycle_opened",
            level="info",
            message=f"Открыт цикл {cycle.year}/{cycle.month:02d} ({start}–{end})",
            cycle=cycle,
        )

    return cycle


def get_cycle_for_date(target_date: date) -> Optional[Cycle]:
    """Возвращает цикл, в который попадает target_date."""
    return Cycle.objects.filter(
        start_date__lte=target_date,
        end_date__gte=target_date,
    ).first()


# =============================================================================
# Закрытие цикла
# =============================================================================

@transaction.atomic
def close_cycle(cycle: Cycle, user=None) -> dict:
    """
    Закрывает цикл:
      1. Переводит статус в 'closing'.
      2. Архивирует все связанные записи.
      3. Очищает default DB.
      4. Открывает следующий цикл.

    Возвращает статистику.
    """
    from .archive.cycle import archive_cycle_data

    if cycle.status == "closed":
        logger.warning("Цикл %s уже закрыт", cycle)
        return {"status": "already_closed", "stats": cycle.archive_stats}

    logger.info("Начинаю закрытие цикла %s", cycle)

    cycle.status = "closing"
    cycle.save(update_fields=["status"])

    from .event_log import log_event
    log_event(
        event_type="cycle_closing",
        level="info",
        message=f"Цикл {cycle} переведён в 'closing'",
        cycle=cycle,
        triggered_by=user,
    )

    # Архивируем все связанные записи
    stats = archive_cycle_data(cycle)

    cycle.status = "closed"
    cycle.closed_at = now()
    cycle.closed_by = user
    cycle.archive_stats = stats
    cycle.save(update_fields=["status", "closed_at", "closed_by", "archive_stats"])

    log_event(
        event_type="cycle_closed",
        level="info",
        message=f"Цикл {cycle} закрыт. Статистика: {stats}",
        cycle=cycle,
        payload=stats,
        triggered_by=user,
    )

    # Открываем следующий цикл
    next_start = cycle.end_date + timedelta(days=1)
    next_cycle = get_or_create_active_cycle(today=next_start)
    logger.info("Открыт следующий цикл: %s", next_cycle)

    return {"status": "closed", "stats": stats, "next_cycle_id": next_cycle.id}


def auto_close_if_due(today: Optional[date] = None) -> Optional[dict]:
    """
    Авто-закрытие, если сегодня 20-е число и предыдущий цикл активен.
    Вызывается через Celery beat.
    """
    if today is None:
        today = date.today()

    if today.day != 20:
        logger.debug("Сегодня не 20-е число (%s), пропуск", today)
        return None

    # Ищем активный цикл, который должен был закрыться вчера
    yesterday = today - timedelta(days=1)
    cycle_to_close = Cycle.objects.filter(
        status="active",
        end_date=yesterday,
    ).first()

    if not cycle_to_close:
        logger.warning(
            "Не найден активный цикл с end_date=%s. "
            "Возможно, цикл уже закрыт или не открыт.",
            yesterday,
        )
        return None

    logger.info("Авто-закрытие цикла: %s", cycle_to_close)
    return close_cycle(cycle_to_close, user=None)