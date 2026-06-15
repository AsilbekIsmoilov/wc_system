import logging
from datetime import timedelta

from hourly_locks.models import Cycle, WorkDebt, WorkDebtDetail

logger = logging.getLogger(__name__)


def archive_debts_for_cycle(cycle: Cycle) -> dict:
    from archive.models import ArchiveWorkDebt, ArchiveWorkDebtDetail

    wd_qs = WorkDebt.objects.filter(cycle=cycle).select_related(
        "operator", "operator__group",
    )

    wd_rows = []
    for wd in wd_qs:
        op = wd.operator
        wd_rows.append(ArchiveWorkDebt(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            operator_fio=op.full_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
            final_debt=wd.current_debt,
            total_accumulated=wd.total_accumulated,
        ))

    if wd_rows:
        ArchiveWorkDebt.objects.using("archive").bulk_create(
            wd_rows, batch_size=500,
        )

    wdd_qs = WorkDebtDetail.objects.filter(cycle=cycle).select_related(
        "operator", "operator__group", "shift",
    )

    wdd_rows = []
    for d in wdd_qs:
        op = d.operator
        wdd_rows.append(ArchiveWorkDebtDetail(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            operator_fio=op.full_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
            day=d.day,
            source=d.source,
            source_object_id=d.source_object_id,
            shift_code=d.shift_code_snapshot or (d.shift.code if d.shift else None),
            violation_type=d.violation_type,
            norm_full=d.norm_full,
            fact_full=d.fact_full,
            debt_full=d.debt_full,
            norm_lock=d.norm_lock,
            fact_lock=d.fact_lock,
            debt_lock=d.debt_lock,
            make_up_wh=d.make_up_wh,
            locked_for_compensation=d.locked_for_compensation,
            note=d.note,
            original_created_at=d.created_at,
        ))

    if wdd_rows:
        ArchiveWorkDebtDetail.objects.using("archive").bulk_create(
            wdd_rows, batch_size=1000,
        )

    result = {
        "work_debt": len(wd_rows),
        "work_debt_detail": len(wdd_rows),
    }
    logger.info("[archive_debt] %s", result)
    return result