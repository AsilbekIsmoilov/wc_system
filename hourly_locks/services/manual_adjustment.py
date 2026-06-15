"""
Ручные правки автоматически рассчитанных значений с обязательным аудитом.

Каждая правка:
  1. Сохраняется в ManualAdjustment (old_value, new_value, reason).
  2. Применяется к целевому объекту.
  3. Логируется в EventLog.
"""

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction

from hourly_locks.models import (
    Compensation,
    ManualAdjustment,
    Transfer,
    WorkDebt,
    WorkDebtDetail,
)

from .event_log import log_event

logger = logging.getLogger(__name__)


# =============================================================================
# Основная функция: adjust(...)
# =============================================================================

@transaction.atomic
def adjust(
    *,
    target,
    field_name: str,
    new_value: Any,
    user,
    reason_code: str,
    reason_text: str,
    requires_approval: bool = False,
) -> ManualAdjustment:
    """
    Универсальная функция для ручной правки любого объекта.

    Args:
        target: объект (Compensation / Transfer / WorkDebt / WorkDebtDetail / ...)
        field_name: имя поля
        new_value: новое значение
        user: User, выполняющий правку
        reason_code: код причины (см. ManualAdjustment.REASON_CHOICES)
        reason_text: текстовое описание
        requires_approval: требует подтверждения другим пользователем
    """
    target_type = _resolve_target_type(target)
    old_value = getattr(target, field_name)

    # Сохраняем правку
    adjustment = ManualAdjustment.objects.create(
        target_type=target_type,
        target_id=target.id,
        operator=_resolve_operator(target),
        field_name=field_name,
        old_value=_serialize(old_value),
        new_value=_serialize(new_value),
        reason_code=reason_code,
        reason_text=reason_text,
        adjusted_by=user,
        requires_approval=requires_approval,
    )

    # Применяем (если не требует подтверждения)
    if not requires_approval:
        setattr(target, field_name, new_value)
        target.save(update_fields=[field_name, "updated_at"] if _has_updated_at(target) else [field_name])

    log_event(
        event_type="manual_adjustment",
        level="warning",
        operator=adjustment.operator,
        target_type=target_type,
        target_id=target.id,
        message=(
            f"Ручная правка {target_type}#{target.id}.{field_name}: "
            f"{old_value} → {new_value} (причина: {reason_code})"
        ),
        payload={
            "field": field_name,
            "old": str(old_value),
            "new": str(new_value),
            "reason_code": reason_code,
            "reason_text": reason_text,
            "requires_approval": requires_approval,
        },
        triggered_by=user,
    )

    return adjustment


# =============================================================================
# Подтверждение правки, требующей approval
# =============================================================================

@transaction.atomic
def approve_adjustment(adjustment: ManualAdjustment, user) -> ManualAdjustment:
    """Подтверждает правку, ранее созданную с requires_approval=True."""
    from django.utils.timezone import now

    if adjustment.approved_at:
        raise ValueError("Правка уже подтверждена")

    if adjustment.adjusted_by_id == user.id:
        raise ValueError("Нельзя подтверждать собственную правку")

    # Применяем
    target = _resolve_target_obj(adjustment.target_type, adjustment.target_id)
    if target:
        new_value = _deserialize(adjustment.new_value)
        setattr(target, adjustment.field_name, new_value)
        target.save(update_fields=[adjustment.field_name])

    adjustment.approved_by = user
    adjustment.approved_at = now()
    adjustment.save(update_fields=["approved_by", "approved_at"])

    log_event(
        event_type="manual_adjustment",
        level="info",
        operator=adjustment.operator,
        target_type=adjustment.target_type,
        target_id=adjustment.target_id,
        message=f"Правка #{adjustment.id} подтверждена",
        triggered_by=user,
    )

    return adjustment


# =============================================================================
# Специализированные функции
# =============================================================================

def adjust_debt_detail(
    debt_detail: WorkDebtDetail,
    *,
    new_debt_full: timedelta = None,
    new_debt_lock: timedelta = None,
    user,
    reason_code: str,
    reason_text: str,
):
    """Изменяет значения debt_full и/или debt_lock в WorkDebtDetail с пересчётом общего долга."""
    old_total = debt_detail.total_debt

    if new_debt_full is not None:
        adjust(
            target=debt_detail,
            field_name="debt_full",
            new_value=new_debt_full,
            user=user,
            reason_code=reason_code,
            reason_text=reason_text,
        )

    if new_debt_lock is not None:
        adjust(
            target=debt_detail,
            field_name="debt_lock",
            new_value=new_debt_lock,
            user=user,
            reason_code=reason_code,
            reason_text=reason_text,
        )

    # Пересчёт WorkDebt.current_debt
    debt_detail.refresh_from_db()
    new_total = debt_detail.total_debt
    delta = new_total - old_total

    if delta != timedelta(0):
        with transaction.atomic():
            wd, _ = WorkDebt.objects.select_for_update().get_or_create(
                operator=debt_detail.operator,
                cycle=debt_detail.cycle,
            )
            wd.current_debt = max(wd.current_debt + delta, timedelta(0))
            wd.save(update_fields=["current_debt", "updated_at"])


# =============================================================================
# Вспомогательные
# =============================================================================

def _resolve_target_type(target) -> str:
    """Определяет target_type по классу объекта."""
    mapping = {
        Compensation: "compensation",
        Transfer: "transfer",
        WorkDebt: "debt_total",
        WorkDebtDetail: "debt_detail",
    }
    for cls, code in mapping.items():
        if isinstance(target, cls):
            return code
    raise ValueError(f"Неизвестный тип объекта: {type(target).__name__}")


def _resolve_operator(target):
    """Возвращает связанного оператора (для денормализации)."""
    return getattr(target, "operator", None)


def _resolve_target_obj(target_type: str, target_id: int):
    """По target_type и target_id возвращает сам объект."""
    mapping = {
        "compensation": Compensation,
        "transfer": Transfer,
        "debt_total": WorkDebt,
        "debt_detail": WorkDebtDetail,
    }
    model_cls = mapping.get(target_type)
    if not model_cls:
        return None
    return model_cls.objects.filter(id=target_id).first()


def _serialize(value) -> Any:
    """Преобразует значение в JSON-сериализуемый формат."""
    if isinstance(value, timedelta):
        return str(value)
    if value is None:
        return None
    return value


def _deserialize(value):
    """Обратная операция _serialize (упрощённо)."""
    if isinstance(value, str) and ":" in value:
        # Попытка распарсить timedelta
        try:
            parts = value.split(":")
            if len(parts) == 3:
                h, m, s = map(int, parts)
                return timedelta(hours=h, minutes=m, seconds=s)
        except ValueError:
            pass
    return value


def _has_updated_at(obj) -> bool:
    """Проверяет, есть ли у объекта поле updated_at."""
    return hasattr(obj, "updated_at")