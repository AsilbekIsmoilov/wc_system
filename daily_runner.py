import logging
import os
import sys
from datetime import date, datetime, timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.utils.timezone import localdate

from hourly_locks.services import (
    compensation_verifier,
    debt_calculator,
    log_loader,
    operator_sync,
    sheets_sync,
    transfer_verifier,
)
from hourly_locks.services.event_log import log_event
from hourly_locks.services.external_api import check_api_integrity
from hourly_locks.sync.runners_sync import push_cycle_to_wfm  # WFM push (Oqim C)


logger = logging.getLogger("daily_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def section(title: str):
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)


def run(target_date: date, skip_sheets: bool = False) -> dict:
    result = {"target_date": str(target_date)}

    section(f"DAILY RUNNER za {target_date}")

    if not skip_sheets:
        section("1. Sheets sync (guruh + grafik)")
        try:
            result["sync_groups"] = sheets_sync.sync_groups_from_sheets()
            logger.info("Guruh: %s", result["sync_groups"])
        except Exception as exc:
            logger.exception("Guruh sync xatosi: %s", exc)
            result["sync_groups"] = {"error": str(exc)}

        try:
            result["sync_schedules"] = sheets_sync.sync_schedules_from_sheets()
            logger.info("Grafik: %s", result["sync_schedules"])
        except Exception as exc:
            logger.exception("Grafik sync xatosi: %s", exc)
            result["sync_schedules"] = {"error": str(exc)}
    else:
        logger.info("Sheets sync o'tkazib yuborildi (--skip-sheets)")

    # 2. API integrity tekshirish
    section("2. API integrity tekshirish")
    integrity = check_api_integrity(target_date)
    result["api_integrity"] = integrity

    if not integrity["ok"]:
        logger.error(
            "API tayyor emas (%d/%d soat ishlamayapti). Pipeline to'xtatildi.",
            integrity["error_count"], 24,
        )
        log_event(
            event_type="api_error",
            level="error",
            message=f"API nedostupen dlya {target_date}: {integrity['errors']}",
            payload=integrity,
        )
        result["status"] = "stopped_api_error"
        return result

    logger.info("API OK: %d/24 soat", integrity["ok_count"])

    # 3. Operatorlarni avto-yaratish
    section("3. Operatorlarni avto-yaratish")
    try:
        result["operator_sync"] = operator_sync.sync_operators_from_api(target_date)
        logger.info("Operator sync: %s", result["operator_sync"])
    except Exception as exc:
        logger.exception("Operator sync xatosi: %s", exc)
        result["operator_sync"] = {"error": str(exc)}

    # 4. Transfer statuslarini yangilash (pending → in_progress → completed)
    section("4. Transfer statuslarini yangilash")
    try:
        result["transfer_statuses"] = transfer_verifier.update_transfer_statuses(
            today=localdate(),
        )
        logger.info("Statuslar: %s", result["transfer_statuses"])
    except Exception as exc:
        logger.exception("Transfer status xatosi: %s", exc)
        result["transfer_statuses"] = {"error": str(exc)}

    # 5. Loglar
    section(f"5. Loglarni yuklash za {target_date}")
    try:
        result["logs"] = log_loader.load_logs_for_day(target_date)
        logger.info("Loglar: %s", result["logs"])
    except Exception as exc:
        logger.exception("Log yuklash xatosi: %s", exc)
        result["logs"] = {"error": str(exc)}

    # 6. Time-off (otprashivanie)
    section(f"6. Time-off za {target_date}")
    try:
        result["time_offs"] = transfer_verifier.apply_time_off_extended_window(target_date)
        logger.info("Time-offs: %s", result["time_offs"])
    except Exception as exc:
        logger.exception("Time-off xatosi: %s", exc)
        result["time_offs"] = {"error": str(exc)}

    # 7. Qarzlar
    section(f"7. Qarzlarni hisoblash za {target_date}")
    try:
        result["debts"] = debt_calculator.calculate_work_debts(target_date)
        logger.info("Qarzlar: %s", result["debts"])
    except Exception as exc:
        logger.exception("Qarz xatosi: %s", exc)
        result["debts"] = {"error": str(exc)}

    # 8. Compensations
    section(f"8. Compensations za {target_date}")
    try:
        result["compensations"] = compensation_verifier.verify_compensations(target_date)
        logger.info("Compensations: %s", result["compensations"])
    except Exception as exc:
        logger.exception("Compensation xatosi: %s", exc)
        result["compensations"] = {"error": str(exc)}

    # 9. Transfers
    section(f"9. Transfers za {target_date}")
    try:
        result["transfers"] = transfer_verifier.verify_transfers_for_date(target_date)
        logger.info("Transfers: %s", result["transfers"])
    except Exception as exc:
        logger.exception("Transfer xatosi: %s", exc)
        result["transfers"] = {"error": str(exc)}

    result["status"] = "completed"

    # Yakuniy event
    log_event(
        event_type="log_loaded",
        level="info",
        message=f"Daily runner zavershen za {target_date}",
        payload={k: v for k, v in result.items() if k not in ("api_integrity",)},
    )

    # WFM ga natijani yuborish (Oqim C)
    try:
        result["wfm_push"] = push_cycle_to_wfm()
        logger.info("WFM push: %s", result["wfm_push"])
    except Exception as exc:
        logger.exception("WFM push xatosi: %s", exc)
        result["wfm_push"] = {"error": str(exc)}

    section(f"GOTOVO za {target_date}")
    return result


def parse_args() -> dict:
    args = {
        "target_date": localdate() - timedelta(days=1),
        "skip_sheets": False,
    }

    for arg in sys.argv[1:]:
        if arg == "--skip-sheets":
            args["skip_sheets"] = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            try:
                args["target_date"] = datetime.strptime(arg, "%Y-%m-%d").date()
            except ValueError:
                logger.error("Noma'lum argument: %s", arg)
                print(__doc__)
                sys.exit(1)

    return args


if __name__ == "__main__":
    args = parse_args()
    result = run(args["target_date"], skip_sheets=args["skip_sheets"])
    logger.info("Final result: %s", result)