"""
Архивация Compensation в архивную БД.
"""

import logging

from hourly_locks.models import Compensation, Cycle

logger = logging.getLogger(__name__)


def archive_compensations_for_cycle(cycle: Cycle) -> int:
    """Архивирует все Compensation цикла."""
    from archive.models import ArchiveCompensation

    qs = Compensation.objects.filter(cycle=cycle).select_related(
        "operator", "operator__group", "type_rule",
    ).prefetch_related("debt_links")

    rows = []
    for comp in qs:
        op = comp.operator
        rule = comp.type_rule

        # Собираем снапшоты CompensationDebtLink
        debt_links_snapshot = []
        for link in comp.debt_links.all():
            debt_links_snapshot.append({
                "debt_detail_id": link.debt_detail_id,
                "snapshot": link.snapshot,
                "applied": link.applied,
                "applied_amount": str(link.applied_amount) if link.applied_amount else None,
            })

        rows.append(ArchiveCompensation(
            archive_year=cycle.year,
            archive_month=cycle.month,
            operator_id=op.id,
            operator_login=op.login_id,
            operator_fio=op.full_name,
            group_id=op.group_id,
            group_name=op.group.name if op.group else None,
            type_code=rule.code,
            type_display=rule.display_name,
            source=comp.source,
            status=comp.status,
            planned_date=comp.planned_date,
            requested_duration=comp.requested_duration,
            verified_duration=comp.verified_duration,
            remaining_debt=comp.remaining_debt,
            deducted=comp.deducted,
            comment=comp.comment,
            debts_snapshot=comp.debts_snapshot or [],
            debt_links_snapshot=debt_links_snapshot,
            claim_metadata=comp.claim_metadata or {},
            auto_check_result=comp.auto_check_result or {},
            auto_check_at=comp.auto_check_at,
            pdf_file_path=comp.pdf_file.name if comp.pdf_file else None,
            screens_path=comp.screens.name if comp.screens else None,
            original_id=comp.id,
            original_created_at=comp.created_at,
            original_updated_at=comp.updated_at,
            verified_at=comp.verified_at,
            verified_by_id=comp.verified_by_id,
            fixed_by_id=comp.fixed_by_id,
        ))

    if rows:
        ArchiveCompensation.objects.using("archive").bulk_create(
            rows, batch_size=500,
        )

    logger.info("[archive_compensation] Архивировано %d записей", len(rows))
    return len(rows)