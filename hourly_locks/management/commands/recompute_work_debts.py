"""
WorkDebt'larni RAW data'dan qayta hisoblash.

Bu command `services.work_debt` modulini ishlatadi —
asosiy logika u yerda yashaydi.

Foydalanish:
    python manage.py recompute_work_debts                # hammasi
    python manage.py recompute_work_debts --cycle 12     # 1 sikl
    python manage.py recompute_work_debts --operator 177 # 1 operator (joriy sikl)
    python manage.py recompute_work_debts --date 2026-06-03  # 1 sana
"""

from datetime import date as date_cls

from django.core.management.base import BaseCommand

from hourly_locks.models import Cycle, Operator
from hourly_locks.services import work_debt
from hourly_locks.services.cycle import (
    get_cycle_for_date,
    get_or_create_active_cycle,
)


class Command(BaseCommand):
    help = "WorkDebt qiymatlarini WDD + CompensationDebtLink dan qayta hisoblash"

    def add_arguments(self, parser):
        parser.add_argument("--cycle", type=int, help="Faqat shu sikl uchun")
        parser.add_argument("--operator", type=int, help="Faqat shu operator uchun")
        parser.add_argument("--date", type=str, help="Faqat shu sana (YYYY-MM-DD)")

    def handle(self, *args, **opts):
        if opts.get("operator"):
            op = Operator.objects.get(id=opts["operator"])
            cycle = None
            if opts.get("cycle"):
                cycle = Cycle.objects.get(id=opts["cycle"])
            else:
                cycle = get_or_create_active_cycle()
            current, accum, changed = work_debt.recompute_for_operator(op, cycle)
            self.stdout.write(self.style.SUCCESS(
                f"{op}: current={current}, accumulated={accum}, changed={changed}"
            ))
            return

        if opts.get("date"):
            d = date_cls.fromisoformat(opts["date"])
            result = work_debt.recompute_for_date(d)
            self.stdout.write(self.style.SUCCESS(f"Date {d}: {result}"))
            return

        if opts.get("cycle"):
            cycle = Cycle.objects.get(id=opts["cycle"])
            result = work_debt.recompute_for_cycle(cycle)
            self.stdout.write(self.style.SUCCESS(f"Cycle {cycle}: {result}"))
            return

        # Hammasi
        result = work_debt.recompute_all()
        self.stdout.write(self.style.SUCCESS(f"All: {result}"))
