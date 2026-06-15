"""
monthly_runner.py — Tsikl yopish va arxivlash (eski monthly_runner.py o'rnida).

Har oyning 20-chi sanasi 00:05 da ishga tushadi (cron).

Tartib:
  1. Yopilishi kerak bo'lgan tsiklni topish (status='active', end_date=yesterday)
  2. close_cycle() chaqirish:
     a. Status 'closing' ga o'zgartirish
     b. Uzun Transfer'larni bo'lish (vacation, training va h.k.)
     c. Compensation ni arxivga ko'chirish
     d. Transfer ni arxivga ko'chirish
     e. WorkDebt + WorkDebtDetail ni arxivga
     f. WorkLogDaily ni arxivga
     g. ManualAdjustment + EventLog (warning+) ni arxivga
     h. Default DB dan tegishli yozuvlar o'chiriladi
     i. Status 'closed' + closed_at + archive_stats yoziladi
  3. Yangi tsikl ochish (next start = end+1)

Ishlatish:
  python monthly_runner.py                  # avto: agar bugun 20 bo'lsa yopadi
  python monthly_runner.py --force          # majburiy yopish (test uchun)
  python monthly_runner.py --cycle-id 5     # konkret tsikl

Cron uchun (Linux):
  5 0 20 * * cd /path/to/project && /path/to/python monthly_runner.py >> /tmp/monthly.log 2>&1
"""

import logging
import os
import sys
from datetime import date

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.utils.timezone import localdate  # noqa: E402

from hourly_locks.models import Cycle  # noqa: E402
from hourly_locks.services import cycle as cycle_service  # noqa: E402
from hourly_locks.sync.runners_sync import push_cycle_status  # noqa: E402  # WFM push


logger = logging.getLogger("monthly_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def section(title: str):
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)


def run_auto() -> dict:
    """Avto-yopish: agar bugun 20-chi sana bo'lsa, eski tsiklni yopadi."""
    today = localdate()
    section(f"MONTHLY RUNNER (avto rezhim, segodnya {today})")

    if today.day != 20:
        logger.info("Segodnya ne 20-e chislo. Propusk.")
        return {"status": "skipped", "reason": "not_20th"}

    result = cycle_service.auto_close_if_due(today=today)
    if result is None:
        logger.warning("Tsikl dlya zakrytiya ne nayden.")
        return {"status": "no_cycle_to_close"}

    logger.info("Rezultat: %s", result)
    return result


def run_force(cycle_id: int = None) -> dict:
    """Majburiy yopish (test uchun)."""
    section("MONTHLY RUNNER (force rezhim)")

    if cycle_id:
        try:
            cycle = Cycle.objects.get(id=cycle_id)
            logger.info("Tsikl topildi: %s", cycle)
        except Cycle.DoesNotExist:
            logger.error("Tsikl #%s topilmadi", cycle_id)
            return {"status": "error", "reason": "cycle_not_found"}
    else:
        cycle = Cycle.get_active()
        if not cycle:
            logger.error("Aktiv tsikl topilmadi")
            return {"status": "error", "reason": "no_active_cycle"}
        logger.info("Aktiv tsikl: %s", cycle)

    if cycle.status == "closed":
        logger.warning("Tsikl allaqachon yopilgan: %s", cycle)
        return {"status": "already_closed", "stats": cycle.archive_stats}

    logger.info("Yopilmoqda: %s", cycle)
    result = cycle_service.close_cycle(cycle, user=None)
    logger.info("Rezultat: %s", result)

    # WFM ga yopilgan cikl statusini yuborish (Oqim C)
    try:
        push_cycle_status(cycle)
    except Exception as exc:
        logger.exception("WFM push (cycle) xatosi: %s", exc)

    return result


def parse_args() -> dict:
    """CLI argumentlarni o'qish."""
    args = {"mode": "auto", "cycle_id": None}

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--force":
            args["mode"] = "force"
        elif arg.startswith("--cycle-id"):
            if "=" in arg:
                args["cycle_id"] = int(arg.split("=")[1])
            else:
                args["mode"] = "force"
                try:
                    args["cycle_id"] = int(sys.argv[i + 2])
                except (IndexError, ValueError):
                    pass
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)

    return args


if __name__ == "__main__":
    args = parse_args()

    if args["mode"] == "force":
        result = run_force(cycle_id=args["cycle_id"])
    else:
        result = run_auto()

    logger.info("Final: %s", result)

    # Statistika
    if isinstance(result, dict) and result.get("status") == "closed":
        section("ARKHIV STATISTIKA")
        stats = result.get("stats", {})
        for key, value in stats.items():
            logger.info("  %s: %s", key, value)