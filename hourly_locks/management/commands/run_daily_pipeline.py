"""
Django management команда: ручной запуск ежедневного конвейера.

Использование:
  python manage.py run_daily_pipeline
  python manage.py run_daily_pipeline --date 2026-05-25
"""

from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import localdate

from hourly_locks.tasks import daily_pipeline_task


class Command(BaseCommand):
    help = "Запуск ежедневного конвейера (загрузка логов + долги + проверка заявок)"

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

        self.stdout.write(f"Запуск ежедневного конвейера за {target_date}...")
        result = daily_pipeline_task(target_date_iso=str(target_date))
        self.stdout.write(self.style.SUCCESS(f"Завершено: {result}"))