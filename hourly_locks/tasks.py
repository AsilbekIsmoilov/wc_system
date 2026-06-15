import logging
from datetime import date, datetime, timedelta

from celery import shared_task
from django.utils.timezone import localdate

from .services import (
    cycle as cycle_service,
    debt_calculator,
    compensation_verifier,
    log_loader,
    night_pipeline,
    operator_sync,
    sheets_sync,
    transfer_verifier,
)
from .services.event_log import log_event
from .services.external_api import check_api_integrity
from .sync.runners_sync import push_cycle_to_wfm  # WFM push (Oqim C)

logger = logging.getLogger(__name__)


# =============================================================================
# Ежедневная синхронизация с Sheets
# =============================================================================

@shared_task(name="hourly_locks.sync_groups")
def sync_groups_task():
    """Синхронизация групп из Google Sheets."""
    logger.info("[task] sync_groups запущена")
    result = sheets_sync.sync_groups_from_sheets()
    logger.info("[task] sync_groups завершена: %s", result)
    return result


@shared_task(name="hourly_locks.sync_schedules")
def sync_schedules_task(year: int = None, month: int = None):
    """Синхронизация расписания за месяц."""
    logger.info("[task] sync_schedules запущена")
    target_month = date(year, month, 1) if year and month else None
    result = sheets_sync.sync_schedules_from_sheets(target_month=target_month)
    logger.info("[task] sync_schedules завершена: %s", result)
    return result


# =============================================================================
# Ежедневный конвейер
# =============================================================================

@shared_task(name="hourly_locks.daily_pipeline")
def daily_pipeline_task(target_date_iso: str = None):

    if target_date_iso:
        target_date = date.fromisoformat(target_date_iso)
    else:
        target_date = localdate() - timedelta(days=1)

    logger.info("[daily_pipeline] Старт за %s", target_date)

    # 1. Проверка API
    integrity = check_api_integrity(target_date)
    if not integrity["ok"]:
        logger.error(
            "[daily_pipeline] API не готов: ошибки в %s часах",
            integrity["error_count"],
        )
        log_event(
            event_type="api_error",
            level="error",
            message="API недоступен для " + str(target_date),
            payload=integrity,
        )
        return {"status": "skipped", "reason": "api_not_ready", "integrity": integrity}

    # 2. Авто-создание новых операторов из API
    op_sync_stats = operator_sync.sync_operators_from_api(target_date)

    # 3. Обновление статусов Transfer
    transfer_verifier.update_transfer_statuses(today=localdate())

    # 4. Загрузка логов
    log_stats = log_loader.load_logs_for_day(target_date)

    # 5. Расчёт долгов
    debt_stats = debt_calculator.calculate_work_debts(target_date)

    # 6. Проверка компенсаций
    comp_stats = compensation_verifier.verify_compensations(target_date)

    # 7. Проверка переносов
    tr_stats = transfer_verifier.verify_transfers_for_date(target_date)

    # 8. Обработка отгулов
    off_stats = transfer_verifier.apply_time_off_extended_window(target_date)

    result = {
        "target_date": str(target_date),
        "operator_sync": op_sync_stats,
        "logs": log_stats,
        "debts": debt_stats,
        "compensations": comp_stats,
        "transfers": tr_stats,
        "time_offs": off_stats,
    }

    # Pipeline oxirida — final recompute (safety net)
    from .services.work_debt import recompute_for_date
    result["work_debt_recompute"] = recompute_for_date(target_date)

    # WFM ga natijani push qilish (Oqim C, incremental)
    try:
        result["wfm_push"] = push_cycle_to_wfm()
    except Exception as exc:
        logger.exception("[daily_pipeline] WFM push xatosi: %s", exc)
        result["wfm_push"] = {"error": str(exc)}

    logger.info("[daily_pipeline] Завершено: %s", result)
    return result


# =============================================================================
# Ночной конвейер 20-08
# =============================================================================

@shared_task(name="hourly_locks.night_pipeline")
def night_pipeline_task(target_date_iso: str = None):
    """Ночной конвейер для 20-08 + компенсация."""
    if target_date_iso:
        target_date = date.fromisoformat(target_date_iso)
    else:
        target_date = localdate() - timedelta(days=1)

    logger.info("[night_pipeline_task] Старт за %s", target_date)
    result = night_pipeline.run_night_pipeline(target_date)

    # WFM ga natijani push qilish (Oqim C)
    try:
        if isinstance(result, dict):
            result["wfm_push"] = push_cycle_to_wfm()
        else:
            push_cycle_to_wfm()
    except Exception as exc:
        logger.exception("[night_pipeline_task] WFM push xatosi: %s", exc)

    logger.info("[night_pipeline_task] Завершено: %s", result)
    return result


# =============================================================================
# Авто-закрытие цикла
# =============================================================================

@shared_task(name="hourly_locks.auto_close_cycle")
def auto_close_cycle_task():
    """
    Запускается каждое 19-е число месяца (beat: monthly-close).
    Закрывает предыдущий цикл и открывает новый, затем пушит в WFM.
    """
    logger.info("[auto_close_cycle_task] Старт")
    result = cycle_service.auto_close_if_due()

    # WFM ga push (yangi aktiv cikl + master data; cikl statuslari yangilanadi)
    try:
        push_cycle_to_wfm()
    except Exception as exc:
        logger.exception("[auto_close_cycle_task] WFM push xatosi: %s", exc)

    logger.info("[auto_close_cycle_task] Результат: %s", result)
    return result