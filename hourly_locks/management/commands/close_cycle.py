
"""
Django management команда: ручное закрытие цикла.

Использование:
  python manage.py close_cycle
  python manage.py close_cycle --cycle-id 5
  python manage.py close_cycle --force
"""

from django.core.management.base import BaseCommand

from hourly_locks.models import Cycle
from hourly_locks.services.cycle import auto_close_if_due, close_cycle


class Command(BaseCommand):
    help = "Ручное закрытие цикла"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cycle-id", type=int, default=None,
            help="ID конкретного цикла для закрытия",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Принудительно закрыть, даже если сегодня не 20-е число",
        )

    def handle(self, *args, **options):
        cycle_id = options["cycle_id"]
        force = options["force"]

        if cycle_id:
            try:
                cycle = Cycle.objects.get(id=cycle_id)
            except Cycle.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Цикл #{cycle_id} не найден"))
                return

            if cycle.status == "closed":
                self.stdout.write(self.style.WARNING(f"Цикл {cycle} уже закрыт"))
                return

            self.stdout.write(f"Закрытие цикла {cycle}...")
            result = close_cycle(cycle, user=None)
            self.stdout.write(self.style.SUCCESS(f"Завершено: {result}"))
            return

        # Авто-закрытие
        if force:
            cycle = Cycle.objects.filter(status="active").first()
            if not cycle:
                self.stderr.write(self.style.ERROR("Активный цикл не найден"))
                return
            self.stdout.write(f"Принудительное закрытие {cycle}...")
            result = close_cycle(cycle, user=None)
        else:
            self.stdout.write("Авто-проверка закрытия цикла...")
            result = auto_close_if_due()

        self.stdout.write(self.style.SUCCESS(f"Результат: {result}"))