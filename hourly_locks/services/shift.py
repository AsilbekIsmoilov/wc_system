"""
Работа со сменами (Shift) и расписанием (OperatorScheduleDay).
"""

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple

from django.db.models import Q

from hourly_locks.models import Operator, OperatorScheduleDay, Shift

logger = logging.getLogger(__name__)


# =============================================================================
# Получение смены оператора на конкретный день
# =============================================================================

def get_operator_shift_for_day(
    operator: Operator,
    day: date,
) -> Optional[Shift]:
    """
    Возвращает Shift для оператора в конкретный день.
    Если выходной — возвращает None.
    """
    schedule = OperatorScheduleDay.objects.filter(
        operator=operator,
        day=day,
    ).select_related("shift").first()

    if not schedule:
        return None

    if schedule.is_day_off:
        return None

    return schedule.shift


def get_schedule_day(
    operator: Operator,
    day: date,
) -> Optional[OperatorScheduleDay]:
    """Возвращает OperatorScheduleDay для оператора в конкретный день."""
    return (
        OperatorScheduleDay.objects
        .filter(operator=operator, day=day)
        .select_related("shift")
        .first()
    )


def get_last_known_shift(
    operator: Operator,
    before_date: date,
) -> Optional[Shift]:
    """
    Возвращает последнюю известную смену оператора до указанной даты.
    Используется как fallback, когда расписание не загружено.
    """
    last = (
        OperatorScheduleDay.objects
        .filter(
            operator=operator,
            day__lt=before_date,
            is_day_off=False,
        )
        .exclude(shift__isnull=True)
        .order_by("-day")
        .select_related("shift")
        .first()
    )

    return last.shift if last else None


# =============================================================================
# Парсинг кода смены
# =============================================================================

def normalize_shift_code(value: str) -> str:
    """
    Нормализует код смены: '08-20.' → '08-20', '8-20' → '08-20'.
    """
    if not isinstance(value, str):
        return ""
    value = value.strip().rstrip(".")
    if not value:
        return ""

    match = re.match(r"^(\d{1,2})\D+(\d{1,2})$", value)
    if match:
        h1, h2 = int(match.group(1)), int(match.group(2))
        return f"{h1:02d}-{h2:02d}"
    return value


def find_shift_by_raw_value(raw: str) -> Optional[Shift]:
    """
    Ищет Shift по сырому значению из Sheets.
    Сначала по нормализованному коду, затем по альтернативным форматам.
    """
    if not raw:
        return None

    normalized = normalize_shift_code(raw)
    if not normalized:
        return None

    # Поиск активной смены
    shift = Shift.objects.filter(code=normalized, is_active=True).first()
    if shift:
        return shift

    # Попытка поиска без активности (для исторических данных)
    return Shift.objects.filter(code=normalized).first()


# =============================================================================
# Окно времени для загрузки логов
# =============================================================================

def get_fetch_window(shift: Shift) -> Tuple[int, int, bool]:
    """
    Возвращает (start_hour, end_hour, crosses_midnight) для загрузки логов.
    Расширяет смену на fetch_hour_padding часов с каждой стороны.
    """
    padding = shift.fetch_hour_padding

    start = (shift.start_time.hour - padding) % 24
    end = (shift.end_time.hour + padding) % 24

    crosses = shift.crosses_midnight
    # Если расширение перевело через полночь
    if start > end and not crosses:
        crosses = True

    return start, end, crosses


def get_fetch_window_for_special(shift_code: str) -> Tuple[int, int, bool]:
    """
    Окно для ночных смен с отработкой/компенсацией — 24-часовая ПЛИТКА
    08:00 (текущий день) → 08:00 (следующий день).

    Почему плитка: дни отработки идут подряд без перекрытия (нет двойного
    счёта), и при этом захватывается отработка ДО начала смены (днём) —
    напр. для 20-08 (20:00→08:00) днём 08:00–20:00 свободно для отработки.
    Часы: текущий день 8..23 + следующий 0..7.
    """
    SPECIAL_WIDE_WINDOWS = {
        "17-02": (8, 7, True),
        "18-03": (8, 7, True),
        "15-24": (8, 7, True),
        "20-08": (8, 7, True),
    }
    if shift_code in SPECIAL_WIDE_WINDOWS:
        return SPECIAL_WIDE_WINDOWS[shift_code]

    # По умолчанию — полный день
    return 6, 23, False


# =============================================================================
# Расчёт времени начала/окончания смены
# =============================================================================

def calculate_shift_datetime_bounds(
    shift: Shift,
    day: date,
) -> Tuple[datetime, datetime]:
    """
    По смене и дню возвращает (start_at, end_at) как datetime.
    Если смена через полночь — end_at будет на следующий день.
    """
    start_dt = datetime.combine(day, shift.start_time)

    if shift.crosses_midnight:
        end_dt = datetime.combine(day + timedelta(days=1), shift.end_time)
    else:
        end_dt = datetime.combine(day, shift.end_time)

    return start_dt, end_dt