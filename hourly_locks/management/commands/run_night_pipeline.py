"""
Django management команда: ручной запуск ночного конвейера 20-08.

Использование:
  python manage.py run_night_pipeline
  python manage.py run_night_pipeline --date 2026-05-25
"""

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import localdate

from hourly_locks.tasks import night_pipeline_task


class Command(BaseCommand):
    help = "Запуск ночного конвейера для смены 20-08 + компенсация"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Дата в формате YYYY-MM-DD. По умолчанию: вчера",
        )

    def handle(self, *args, **options):
        if options["date"]:
            try:
                target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                self.stderr.write(self.style.ERROR(
                    "Неверный формат даты. Используйте YYYY-MM-DD",
                ))
                return
        else:
            target_date = localdate() - timedelta(days=1)

        self.stdout.write(f"Запуск ночного конвейера за {target_date}...")
        result = night_pipeline_task(target_date_iso=str(target_date))
        self.stdout.write(self.style.SUCCESS(f"Завершено: {result}"))