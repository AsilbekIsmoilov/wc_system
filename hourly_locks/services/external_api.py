"""
Клиент внешнего API почасовых логов.

URL и таймаут хранятся в SystemPolicy.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import requests
from django.utils.dateparse import parse_duration

from hourly_locks.utils import get_system_policy

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "http://192.168.42.172:5000/csv-to-json/hour_by"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_START_COLUMN = 0
DEFAULT_COLUMN_LIMIT = 17


def get_base_url() -> str:
    """URL внешнего API из SystemPolicy или дефолт."""
    return get_system_policy("external_api_url", DEFAULT_BASE_URL)


def get_timeout() -> int:
    """Таймаут запросов в секундах."""
    return int(get_system_policy("external_api_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))


# =============================================================================
# Запросы к API
# =============================================================================

def fetch_hour(day: date, hour: int) -> Optional[list]:
    """
    Получает данные за один час.
    Возвращает список строк (по операторам) или None при ошибке.
    """
    url = get_base_url()
    timeout = get_timeout()

    params = {
        "start_column": DEFAULT_START_COLUMN,
        "column_limit": DEFAULT_COLUMN_LIMIT,
        "year": day.year,
        "month": f"{day.month:02d}",
        "day": f"{day.day:02d}",
        "hour": f"{hour:02d}",
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()

        if "error" in payload:
            logger.error(
                "API вернул ошибку для %s %02d:00 — %s",
                day, hour, payload.get("error"),
            )
            return None

        return payload.get("data", [])

    except Exception as exc:
        logger.error("Ошибка запроса к API для %s %02d:00 — %s", day, hour, exc)
        return None


def fetch_hours_range(day: date, hours: range) -> dict:
    """
    Получает данные для диапазона часов за один день.
    Возвращает dict: {hour: [rows...]}
    """
    result = {}
    for hour in hours:
        rows = fetch_hour(day, hour)
        if rows is not None:
            result[hour] = rows
        else:
            result[hour] = []
    return result


def check_api_integrity(day: date) -> dict:
    """
    Проверяет, что все 24 часа за день доступны через API.
    Возвращает: {"ok": bool, "ok_hours": [...], "errors": [...]}
    """
    ok_hours = []
    errors = []

    for hour in range(24):
        rows = fetch_hour(day, hour)
        if rows is None:
            errors.append(hour)
        else:
            ok_hours.append(hour)

    return {
        "ok": not errors,
        "ok_hours": ok_hours,
        "errors": errors,
        "ok_count": len(ok_hours),
        "error_count": len(errors),
    }


# =============================================================================
# Утилиты для агрегации
# =============================================================================

def sum_for_login(rows: list, login_id: str) -> dict:
    """
    Суммирует длительности для конкретного оператора по login_id.
    Возвращает dict со всеми длительностями.
    """
    result = {
        "aftercall_duration": timedelta(),
        "busy_duration": timedelta(),
        "hold_duration": timedelta(),
        "idle_duration": timedelta(),
        "lazy_duration": timedelta(),
        "lock_duration": timedelta(),
        "relax_duration": timedelta(),
        "full_duration": timedelta(),
    }

    field_map = {
        "AfterCallDuration": "aftercall_duration",
        "BusyDuration": "busy_duration",
        "HoldDuration": "hold_duration",
        "IdleDuration": "idle_duration",
        "LazyDuration": "lazy_duration",
        "LockDuration": "lock_duration",
        "RelaxDuration": "relax_duration",
        "FullDuration": "full_duration",
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("login") or "").strip() != login_id:
            continue

        for api_key, field_key in field_map.items():
            value = parse_duration(row.get(api_key, "00:00:00"))
            if value:
                result[field_key] += value

    return result