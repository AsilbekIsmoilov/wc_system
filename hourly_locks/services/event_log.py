"""
Журнал событий (EventLog).

Используется всеми сервисами для записи значимых событий.
"""

import logging
from typing import Any, Optional

from hourly_locks.models import Cycle, EventLog, Operator

logger = logging.getLogger(__name__)


def log_event(
    event_type: str,
    *,
    level: str = "info",
    message: str = "",
    operator: Optional[Operator] = None,
    cycle: Optional[Cycle] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    payload: Optional[dict] = None,
    triggered_by: Optional[Any] = None,
) -> EventLog:
    """
    Записывает событие в EventLog.

    Args:
        event_type: код события (см. EventLog.EVENT_TYPE_CHOICES)
        level: debug / info / warning / error / critical
        message: текстовое описание
        operator: связанный оператор
        cycle: связанный цикл
        target_type: тип связанного объекта (compensation, transfer, ...)
        target_id: ID связанного объекта
        payload: произвольные данные
        triggered_by: User-инициатор
    """
    try:
        return EventLog.objects.create(
            event_type=event_type,
            level=level,
            message=message or "",
            operator=operator,
            cycle=cycle,
            target_type=target_type,
            target_id=target_id,
            payload=payload or {},
            triggered_by=triggered_by,
        )
    except Exception as exc:
        # Логирование не должно падать
        logger.error("Не удалось записать EventLog: %s", exc)
        return None