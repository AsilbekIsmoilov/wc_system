"""
Архивация Transfer в архивную БД.

Учитывает длинные Transfer (vacation, training и т.п.), которые
переходят через границу цикла — такие разрезаются: одна часть
архивируется, другая остаётся в новом цикле.
"""

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils.timezone import now

from hourly_locks.models import Cycle, RequestTypeRule, Transfer

logger = logging.getLogger(__name__)


def archive_transfers_for_cycle(cycle: Cycle) -> int:
    """
    Архивирует все Transfer'ы цикла.
    Длинные Transfer'ы, выходящие за границу — разрезаются.
    """
    # Сначала разрезаем длинные
    split_count = _split_long_transfers(cycle)

    # Затем архивируем все, что относится к этому циклу
    archived_count = _archive_all_transfers(cycle)

    logger.info(
        "[archive_transfer] Разрезано: %d, архивировано: %d",
        split_count, archived_count,
    )
    return archived_count


def _split_long_transfers(cycle: Cycle) -> int:
    """
    Находит Transfer'ы, которые начались в этом цикле, но закончатся
    в следующем. Разрезает их: одна часть копируется в архив (как
    completed), а исходный Transfer переносится на новый цикл.
    """
    # Типы, которые могут быть длинными (vacation, training и т.п.)
    long_rules = RequestTypeRule.objects.filter(
        category="transfer",
        exempts_from_daily_debt=True,
    )

    long_transfers = Transfer.objects.filter(
        type_rule__in=long_rules,
        status__in=["pending", "in_progress", "approved"],
        date_from__lt=cycle.end_date,
        date_to__gt=cycle.end_date,
        cycle=cycle,
    ).select_related("operator", "operator__group", "type_rule")

    count = 0
    next_cycle_start = cycle.end_date + timedelta(days=1)

    for transfer in long_transfers:
        try:
            _split_single(transfer, cycle, next_cycle_start)
            count += 1
        except Exception as exc:
            logger.exception(
                "[archive_transfer_split] Ошибка для %s: %s", transfer, exc,
            )

    return count


@transaction.atomic
def _split_single(transfer: Transfer, cycle: Cycle, next_cycle_start: date):
    """Разрезает один Transfer на архивную и продолжающую части."""
    from archive.models import ArchiveTransfer

    op = transfer.operator
    rule = transfer.type_rule

    # 1. Архивируем «прошлую» часть как completed
    ArchiveTransfer.objects.using("archive").create(
        archive_year=cycle.year,
        archive_month=cycle.month,
        operator_id=op.id,
        operator_login=op.login_id,
        operator_fio=op.full_name,
        group_id=op.group_id,
        group_name=op.group.name if op.group else None,
        type_code=rule.code,
        type_display=rule.display_name,
        status="completed",
        date_from=transfer.date_from,
        date_to=cycle.end_date,
        hour_from=transfer.hour_from,
        hour_to=transfer.hour_to,
        requested_duration=transfer.requested_duration,
        verified_duration=transfer.verified_duration,
        comment=transfer.comment,
        file_path=transfer.pdf_file.name if transfer.pdf_file else None,
        screens_path=transfer.screens.name if transfer.screens else None,
        original_id=transfer.id,
        original_created_at=transfer.created_at,
        original_updated_at=transfer.updated_at,
        verified_at=transfer.verified_at or now(),
        verified_by_id=transfer.verified_by_id,
        fixed_by_id=transfer.fixed_by_id,
        was_split=True,
    )

    # 2. Сдвигаем исходный Transfer на новый цикл
    new_cycle = Cycle.objects.filter(
        start_date__lte=next_cycle_start,
        end_date__gte=next_cycle_start,
    ).first()

    transfer.date_from = next_cycle_start
    if new_cycle:
        transfer.cycle = new_cycle
    transfer.save(update_fields=["date_from", "cycle", "updated_at"])


def _archive_all_transfers(cycle: Cycle) -> int:
    """Архивирует все Transfer'ы, относящиеся к циклу."""
    from archive.models import ArchiveTransfer

    qs = Transfer.objects.filter(cycle=cycle).select_related(
        "operator", "operator__group", "type_rule",
    )

    rows = []
    for transfer in qs:
        op = transfer.operator
        rule = transfer.type_rule

        rows.append(ArchiveTransfer(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            operator_fio=op.full_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
            type_code=rule.code,
            type_display=rule.display_name,
            status=transfer.status,
            date_from=transfer.date_from,
            date_to=transfer.date_to,
            hour_from=transfer.hour_from,
            hour_to=transfer.hour_to,
            requested_duration=transfer.requested_duration,
            verified_duration=transfer.verified_duration,
            remaining_debt=transfer.remaining_debt,
            comment=transfer.comment,
            file_path=transfer.pdf_file.name if transfer.pdf_file else None,
            screens_path=transfer.screens.name if transfer.screens else None,
            original_id=transfer.id,
            original_created_at=transfer.created_at,
            original_updated_at=transfer.updated_at,
            verified_at=transfer.verified_at,
            verified_by_id=transfer.verified_by_id,
            fixed_by_id=transfer.fixed_by_id,
            was_split=False,
        ))

    if rows:
        ArchiveTransfer.objects.using("archive").bulk_create(
            rows, batch_size=500,
        )

    return len(rows)