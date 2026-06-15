"""
Django management команда: синхронизация расписания и групп из Google Sheets.

Использование:
  python manage.py sync_schedules
  python manage.py sync_schedules --groups-only
  python manage.py sync_schedules --schedules-only
  python manage.py sync_schedules --year 2026 --month 5
"""

from datetime import date

from django.core.management.base import BaseCommand

from hourly_locks.services.sheets_sync import (
    sync_groups_from_sheets,
    sync_schedules_from_sheets,
)


class Command(BaseCommand):
    help = "Синхронизация расписания и групп из Google Sheets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--groups-only", action="store_true",
            help="Только группы",
        )
        parser.add_argument(
            "--schedules-only", action="store_true",
            help="Только расписание",
        )
        parser.add_argument(
            "--year", type=int, default=None,
            help="Год для расписания (по умолчанию текущий)",
        )
        parser.add_argument(
            "--month", type=int, default=None,
            help="Месяц для расписания (по умолчанию текущий)",
        )

    def handle(self, *args, **options):
        groups_only = options["groups_only"]
        schedules_only = options["schedules_only"]

        if not schedules_only:
            self.stdout.write("Синхронизация групп...")
            result = sync_groups_from_sheets()
            self.stdout.write(self.style.SUCCESS(f"Группы: {result}"))

        if not groups_only:
            if options["year"] and options["month"]:
                target = date(options["year"], options["month"], 1)
            else:
                target = None

            self.stdout.write("Синхронизация расписания...")
            result = sync_schedules_from_sheets(target_month=target)
            self.stdout.write(self.style.SUCCESS(f"Расписание: {result}"))