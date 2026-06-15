"""
Авто-создание операторов на основе данных внешнего API.

Когда API возвращает login_id, которого нет в БД — создаём Operator
с распарсенным ФИО, без группы, и пишем EventLog (warning),
чтобы супервайзер обратил внимание.

ВАЖНО:
  - Существующие операторы НЕ перезаписываются (в отличие от старого кода).
  - ФИО разбивается на surname/name/middle_name только при создании.
  - Можно отключить через SystemPolicy "auto_create_operators_from_api".
"""

import logging
from datetime import date
from typing import Set

from django.db import transaction

from hourly_locks.models import Operator
from hourly_locks.utils import get_system_policy

from . import external_api
from .event_log import log_event

logger = logging.getLogger(__name__)


def sync_operators_from_api(target_date: date, sample_hours: range = None) -> dict:
    """
    Просматривает API за указанный день и создаёт новых операторов,
    которых нет в БД.

    Args:
        target_date: дата для проверки
        sample_hours: какие часы запрашивать (по умолчанию 10-15 — рабочее время,
                      чтобы охватить все смены)

    Returns:
        dict со статистикой: {created: N, existing: N, total_unique: N}
    """
    enabled = get_system_policy("auto_create_operators_from_api", True)
    if not enabled:
        logger.info("[operator_sync] Отключено через SystemPolicy")
        return {"created": 0, "existing": 0, "skipped": "disabled"}

    if sample_hours is None:
        sample_hours = range(10, 16)  # 10:00-15:00 — большинство смен активны

    logger.info("[operator_sync] Сканирование API за %s, часы %s", target_date, list(sample_hours))

    # Собираем уникальные логины с ФИО
    unique_operators = {}  # login_id -> FullName

    for hour in sample_hours:
        rows = external_api.fetch_hour(target_date, hour)
        if not rows:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            login = (row.get("login") or "").strip()
            fio = (row.get("FullName") or "").strip()
            if not login or not fio:
                continue
            # Первое появление имени запоминаем
            if login not in unique_operators:
                unique_operators[login] = fio

    if not unique_operators:
        logger.info("[operator_sync] В API нет операторов за %s", target_date)
        return {"created": 0, "existing": 0, "total_unique": 0}

    # Существующие login_id
    existing_logins = set(
        Operator.objects
        .filter(login_id__in=list(unique_operators.keys()))
        .values_list("login_id", flat=True)
    )

    new_logins = set(unique_operators.keys()) - existing_logins

    created = 0
    with transaction.atomic():
        for login_id in new_logins:
            fio = unique_operators[login_id]
            surname, name, middle_name = _parse_fio(fio)

            try:
                Operator.objects.create(
                    login_id=login_id,
                    surname=surname,
                    name=name,
                    middle_name=middle_name,
                    is_active=True,
                )
                created += 1

                log_event(
                    event_type="sheets_synced",  # Используем близкий тип
                    level="warning",
                    message=(
                        f"Авто-создан новый оператор из API: "
                        f"{fio} (login_id={login_id}). "
                        f"Назначьте группу через админку."
                    ),
                    target_type="operator",
                    payload={
                        "login_id": login_id,
                        "fio": fio,
                        "auto_created_at": str(target_date),
                    },
                )
                logger.warning(
                    "[operator_sync] Создан оператор: %s %s %s (login=%s)",
                    surname, name, middle_name or "", login_id,
                )

            except Exception as exc:
                logger.exception(
                    "[operator_sync] Ошибка создания оператора %s: %s",
                    fio, exc,
                )

    stats = {
        "created": created,
        "existing": len(existing_logins),
        "total_unique": len(unique_operators),
    }
    logger.info("[operator_sync] Завершено: %s", stats)
    return stats


def _parse_fio(full_name: str) -> tuple:
    """Разбирает ФИО: 'Иванов Иван Иванович' -> ('Иванов', 'Иван', 'Иванович')."""
    parts = full_name.strip().split(maxsplit=2)
    surname = parts[0] if len(parts) >= 1 else ""
    name = parts[1] if len(parts) >= 2 else ""
    middle_name = parts[2] if len(parts) >= 3 else None
    return surname, name, middle_name