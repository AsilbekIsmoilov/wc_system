
import logging
import os
import sys
from datetime import date, datetime, timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.utils.timezone import localdate  # noqa: E402

from hourly_locks.services import night_pipeline  # noqa: E402
from hourly_locks.services.event_log import log_event  # noqa: E402
from hourly_locks.sync.runners_sync import push_cycle_to_wfm


logger = logging.getLogger("night_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def section(title: str):
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)


def run(target_date: date) -> dict:
    """
    20-08 tungi pipeline ni ishga tushiradi.
    """
    section(f"NIGHT RUNNER 20-08 za {target_date}")

    try:
        result = night_pipeline.run_night_pipeline(target_date)
        logger.info("Natija: %s", result)

        log_event(
            event_type="night_pipeline_run",
            level="info",
            message=f"Night runner zavershen za {target_date}",
            payload=result,
        )

        # WFM ga natijani yuborish (Oqim C)
        try:
            result["wfm_push"] = push_cycle_to_wfm()
        except Exception as exc2:
            logger.exception("WFM push xatosi: %s", exc2)

        return result

    except Exception as exc:
        logger.exception("Night runner xatosi: %s", exc)
        log_event(
            event_type="night_pipeline_run",
            level="error",
            message=f"Night runner xatosi za {target_date}: {exc}",
        )
        return {"status": "error", "error": str(exc)}


def parse_args() -> date:
    """CLI argumentdan sanani olish."""
    if len(sys.argv) < 2:
        return localdate() - timedelta(days=1)

    arg = sys.argv[1]
    if arg in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    try:
        return datetime.strptime(arg, "%Y-%m-%d").date()
    except ValueError:
        logger.error("Noto'g'ri sana formati: %s. YYYY-MM-DD kerak.", arg)
        sys.exit(1)


if __name__ == "__main__":
    target_date = parse_args()
    result = run(target_date)

    section("FINAL")
    if isinstance(result, dict):
        for key, value in result.items():
            logger.info("  %s: %s", key, value)