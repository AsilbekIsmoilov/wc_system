"""
Главный архиватор цикла: при закрытии цикла все связанные данные
переносятся в архивную БД, а в default БД остаются только данные
нового активного цикла.

ВАРИАНТ A: все долги полностью архивируются, новый цикл начинается с 0.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils.timezone import now

from hourly_locks.models import (
    Compensation,
    CompensationDebtLink,
    Cycle,
    EventLog,
    ManualAdjustment,
    Operator,
    Transfer,
    WorkDebt,
    WorkDebtDetail,
    WorkLogDaily,
)

from .compensation import archive_compensations_for_cycle
from .debt import archive_debts_for_cycle
from .transfer import archive_transfers_for_cycle

logger = logging.getLogger(__name__)


def archive_cycle_data(cycle: Cycle) -> dict:
    """
    Архивирует все данные цикла, затем удаляет их из default DB.

    Стадии:
      0. Cross-cycle re-pointing (заявки с planned_date в новом цикле
         переносятся, а не архивируются).
      1. Снапшот операторов (для исторических ссылок).
      2. Архивация Compensation.
      3. Архивация Transfer.
      4. Архивация WorkDebt / WorkDebtDetail.
      5. Архивация WorkLogDaily (опционально).
      6. Архивация ManualAdjustment.
      7. Архивация значимых EventLog.
      8. Очистка default DB (только относящееся к закрываемому циклу).
    """
    logger.info("[archive_cycle] Начало архивации цикла %s", cycle)

    stats = {}

    # 0. Cross-cycle re-pointing — ВАЖНО: до архивации!
    stats["repointed"] = _repoint_cross_cycle_requests(cycle)

    # 1. Снапшот операторов
    stats["operators_snapshot"] = _archive_operator_snapshots(cycle)

    # 2. Compensation
    stats["compensations"] = archive_compensations_for_cycle(cycle)

    # 3. Transfer
    stats["transfers"] = archive_transfers_for_cycle(cycle)

    # 4. WorkDebt / WorkDebtDetail
    stats["debts"] = archive_debts_for_cycle(cycle)

    # 5. WorkLogDaily
    stats["logs"] = _archive_work_logs(cycle)

    # 6. ManualAdjustment
    stats["manual_adjustments"] = _archive_manual_adjustments(cycle)

    # 7. EventLog (только warning+)
    stats["event_logs"] = _archive_event_logs(cycle)

    # 8. Очистка default DB
    _cleanup_default_db(cycle)

    logger.info(
        "[archive_cycle] Завершено для цикла %s. Статистика: %s",
        cycle, stats,
    )
    return stats


# =============================================================================
# Cross-cycle re-pointing
# =============================================================================

@transaction.atomic
def _repoint_cross_cycle_requests(cycle: Cycle) -> dict:
    """
    Заявки, у которых planned_date / date_to УЖЕ В НОВОМ цикле,
    не нужно архивировать — нужно перепривязать к новому циклу.

    Compensation с CompensationDebtLink на WDD текущего цикла:
      - Перепривязываются на новый цикл
      - В snapshot каждого link записывается archive_year/month +
        archive_wdd_id, чтобы потом найти долг в архиве
      - debt_detail в default DB станет null после архивации
      - При verify в новом цикле _apply_debt_links увидит archive_ref
        и обновит ArchiveWorkDebt + ArchiveWorkDebtDetail (cross-DB credit)

    Возвращает {compensations: N, transfers: N, links_marked: N}.
    """
    from hourly_locks.services.cycle import get_or_create_active_cycle

    next_cycle_start = cycle.end_date + timedelta(days=1)
    next_cycle = get_or_create_active_cycle(today=next_cycle_start)

    # 1. Все Compensation с planned_date в новом цикле
    comp_qs = Compensation.objects.filter(
        cycle=cycle,
        status__in=["pending", "in_progress"],
        planned_date__gt=cycle.end_date,
    )

    # 1a. Помечаем все debt_links на архивирующиеся WDD — добавляем archive_ref в snapshot
    from hourly_locks.models import CompensationDebtLink, WorkDebtDetail

    links_to_mark = CompensationDebtLink.objects.filter(
        compensation__in=comp_qs,
        applied=False,
        debt_detail__cycle=cycle,  # WDD текущего цикла = будет архивирован
    ).select_related("debt_detail")

    links_marked = 0
    for link in links_to_mark:
        wdd = link.debt_detail
        if not wdd:
            continue
        # Обновляем snapshot — добавляем archive-ссылки
        snap = dict(link.snapshot or {})
        snap.update({
            "archive_year": cycle.year,
            "archive_month": cycle.month,
            "operator_id": wdd.operator_id,
            "day": str(wdd.day),
            "source": wdd.source,
            "shift_code_snapshot": wdd.shift_code_snapshot,
            "debt_full": str(wdd.debt_full),
            "debt_lock": str(wdd.debt_lock),
            "original_wdd_id": wdd.id,
        })
        link.snapshot = snap
        link.save(update_fields=["snapshot", "updated_at"])
        links_marked += 1

    # 1b. Перепривязываем все Compensation на новый цикл
    comp_count = comp_qs.count()
    if comp_count:
        comp_qs.update(cycle=next_cycle)
        logger.info(
            "[archive_cycle] Перепривязано %d Compensation на новый цикл #%d "
            "(в т.ч. %d debt_links отмечены для cross-DB credit)",
            comp_count, next_cycle.id, links_marked,
        )

    # 2. Transfer: date_from в новом цикле → перепривязываем
    tr_qs = Transfer.objects.filter(
        cycle=cycle,
        status__in=["pending", "in_progress"],
        date_from__gt=cycle.end_date,
    )
    tr_count = tr_qs.count()
    if tr_count:
        tr_qs.update(cycle=next_cycle)
        logger.info(
            "[archive_cycle] Перепривязано %d Transfer на новый цикл #%d",
            tr_count, next_cycle.id,
        )

    return {
        "compensations": comp_count,
        "transfers": tr_count,
        "links_marked_for_archive_credit": links_marked,
    }


# =============================================================================
# Снапшот операторов
# =============================================================================

def _archive_operator_snapshots(cycle: Cycle) -> int:
    """Сохраняет снапшот всех активных операторов на момент закрытия."""
    from archive.models import ArchiveOperatorSnapshot

    operators = Operator.objects.filter(is_active=True).select_related("group")
    count = 0

    snapshots = []
    for op in operators:
        snapshots.append(ArchiveOperatorSnapshot(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            surname=op.surname,
            name=op.name,
            middle_name=op.middle_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
        ))

    if snapshots:
        ArchiveOperatorSnapshot.objects.using("archive").bulk_create(
            snapshots, batch_size=500, ignore_conflicts=True,
        )
        count = len(snapshots)

    return count


# =============================================================================
# WorkLogDaily
# =============================================================================

def _archive_work_logs(cycle: Cycle) -> int:
    """Архивирует WorkLogDaily за цикл."""
    from archive.models import ArchiveWorkLogDaily

    logs = WorkLogDaily.objects.filter(cycle=cycle).select_related(
        "operator", "operator__group",
    )

    rows = []
    for log in logs:
        op = log.operator
        rows.append(ArchiveWorkLogDaily(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            operator_fio=op.full_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
            day=log.day,
            shift_code=log.shift_code_snapshot,
            start_at=log.start_at,
            end_at=log.end_at,
            aftercall_duration=log.aftercall_duration,
            busy_duration=log.busy_duration,
            hold_duration=log.hold_duration,
            idle_duration=log.idle_duration,
            lazy_duration=log.lazy_duration,
            lock_duration=log.lock_duration,
            relax_duration=log.relax_duration,
            full_duration=log.full_duration,
            is_special_aggregation=log.is_special_aggregation,
        ))

    if rows:
        ArchiveWorkLogDaily.objects.using("archive").bulk_create(
            rows, batch_size=500,
        )

    return len(rows)


# =============================================================================
# ManualAdjustment
# =============================================================================

def _archive_manual_adjustments(cycle: Cycle) -> int:
    """Архивирует все ручные правки за цикл."""
    from archive.models import ArchiveManualAdjustment

    # Все правки, сделанные в период цикла
    adjustments = ManualAdjustment.objects.filter(
        adjusted_at__date__gte=cycle.start_date,
        adjusted_at__date__lte=cycle.end_date,
    ).select_related("operator", "adjusted_by")

    rows = []
    for adj in adjustments:
        op = adj.operator
        rows.append(ArchiveManualAdjustment(
            archive_year=cycle.year,
            archive_month=cycle.month,
            target_type=adj.target_type,
            target_id=adj.target_id,
            operator_id=op.id if op else None,
            operator_login=op.login_id if op else None,
            field_name=adj.field_name,
            old_value=adj.old_value,
            new_value=adj.new_value,
            reason_code=adj.reason_code,
            reason_text=adj.reason_text,
            adjusted_by_id=adj.adjusted_by_id,
            adjusted_by_username=adj.adjusted_by.username if adj.adjusted_by else "",
            adjusted_at=adj.adjusted_at,
            approved_by_id=adj.approved_by_id,
            approved_at=adj.approved_at,
            original_id=adj.id,
        ))

    if rows:
        ArchiveManualAdjustment.objects.using("archive").bulk_create(
            rows, batch_size=500,
        )

    return len(rows)


# =============================================================================
# EventLog (только warning+)
# =============================================================================

def _archive_event_logs(cycle: Cycle) -> int:
    """Архивирует только важные события (warning/error/critical) за цикл."""
    from archive.models import ArchiveEventLog

    events = EventLog.objects.filter(
        timestamp__date__gte=cycle.start_date,
        timestamp__date__lte=cycle.end_date,
        level__in=["warning", "error", "critical"],
    ).select_related("operator")

    rows = []
    for ev in events:
        op = ev.operator
        rows.append(ArchiveEventLog(
            archive_year=cycle.year,
            archive_month=cycle.month,
            event_type=ev.event_type,
            level=ev.level,
            operator_id=op.id if op else None,
            operator_login=op.login_id if op else None,
            target_type=ev.target_type,
            target_id=ev.target_id,
            message=ev.message,
            payload=ev.payload,
            original_timestamp=ev.timestamp,
            triggered_by_id=ev.triggered_by_id,
        ))

    if rows:
        ArchiveEventLog.objects.using("archive").bulk_create(
            rows, batch_size=500,
        )

    return len(rows)


# =============================================================================
# Очистка default DB
# =============================================================================

@transaction.atomic
def _cleanup_default_db(cycle: Cycle):
    """
    Удаляет все данные цикла из default DB.
    Вариант A: всё стирается, новый цикл начинается с нуля.
    """
    logger.info("[archive_cycle] Очистка default DB для цикла %s", cycle)

    # 1. CompensationDebtLink (через каскад от Compensation, но на всякий случай)
    CompensationDebtLink.objects.filter(compensation__cycle=cycle).delete()

    # 2. Compensation
    deleted_comp, _ = Compensation.objects.filter(cycle=cycle).delete()

    # 3. Transfer
    deleted_tr, _ = Transfer.objects.filter(cycle=cycle).delete()

    # 4. WorkDebtDetail
    deleted_wdd, _ = WorkDebtDetail.objects.filter(cycle=cycle).delete()

    # 5. WorkDebt
    deleted_wd, _ = WorkDebt.objects.filter(cycle=cycle).delete()

    # 6. WorkLogDaily
    deleted_logs, _ = WorkLogDaily.objects.filter(cycle=cycle).delete()

    # 7. ManualAdjustment за цикл (опционально — можно оставить в default для аудита)
    # ManualAdjustment.objects.filter(
    #     adjusted_at__date__gte=cycle.start_date,
    #     adjusted_at__date__lte=cycle.end_date,
    # ).delete()

    logger.info(
        "[archive_cycle] Удалено: comp=%d, transfer=%d, wdd=%d, wd=%d, logs=%d",
        deleted_comp, deleted_tr, deleted_wdd, deleted_wd, deleted_logs,
    )