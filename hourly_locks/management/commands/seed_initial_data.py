"""
Django management команда: первичное наполнение БД базовыми данными.

Заполняет:
  - Shift  — стандартные смены
  - RequestTypeRule — типы заявок
  - SystemPolicy — базовые настройки
  - Cycle — текущий активный цикл

Использование:
  python manage.py seed_initial_data
  python manage.py seed_initial_data --reset  (опасно — удалит существующее)
"""

from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from hourly_locks.models import RequestTypeRule, Shift, SystemPolicy
from hourly_locks.services.cycle import get_or_create_active_cycle


SHIFTS = [
    # code, display_name, start, end, crosses_midnight, norm_full, norm_lock_soft_cap, norm_lock_warn_at, tolerance, is_night, special
    ("06-15", "Утро 06:00-15:00", time(6), time(15), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), False, False),
    ("07-15", "Утро 07:00-15:00", time(7), time(15), False, timedelta(hours=8), timedelta(hours=1, minutes=46), timedelta(0), timedelta(0), False, False),
    ("07-16", "Утро 07:00-16:00", time(7), time(16), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), False, False),
    ("08-16", "Утро 08:00-16:00", time(8), time(16), False, timedelta(hours=8), timedelta(hours=1, minutes=46), timedelta(0), timedelta(0), False, False),
    ("08-17", "День 08:00-17:00", time(8), time(17), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), False, False),
    ("09-17", "День 09:00-17:00", time(9), time(17), False, timedelta(hours=8), timedelta(hours=1, minutes=46), timedelta(0), timedelta(0), False, False),
    ("09-18", "День 09:00-18:00", time(9), time(18), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), False, False),
    ("10-19", "День 10:00-19:00", time(10), time(19), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), False, False),
    ("11-20", "День 11:00-20:00", time(11), time(20), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(minutes=10), False, False),
    ("13-22", "Вечер 13:00-22:00", time(13), time(22), False, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(minutes=10), False, False),
    ("15-24", "Вечер 15:00-00:00", time(15), time(0), True, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(minutes=10), True, False),
    ("17-02", "Ночь 17:00-02:00", time(17), time(2), True, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), True, False),
    ("18-03", "Ночь 18:00-03:00", time(18), time(3), True, timedelta(hours=9), timedelta(hours=1, minutes=46), timedelta(hours=1, minutes=30), timedelta(0), True, False),
    ("08-20", "Дневная 12ч 08:00-20:00", time(8), time(20), False, timedelta(hours=12), timedelta(hours=2, minutes=20), timedelta(0), timedelta(minutes=10), False, False),
    ("20-08", "Ночная 12ч 20:00-08:00", time(20), time(8), True, timedelta(hours=12), timedelta(hours=2, minutes=20), timedelta(0), timedelta(0), True, True),
]


REQUEST_TYPE_RULES = [
    # Компенсации
    dict(
        category="compensation", code="compensation",
        display_name="Отработка",
        verification_strategy="schedule_based",
        sort_order=10,
    ),
    dict(
        category="compensation", code="nb_compensation",
        display_name="Отработать н/б",
        description=(
            "NB-компенсация: оператор пропустил полный рабочий день "
            "(9ч или 12ч недоработки) и отрабатывает в свой выходной."
        ),
        verification_strategy="net_based",
        min_duration=timedelta(hours=9),
        max_duration=timedelta(hours=12),
        sort_order=20,
    ),
    dict(
        category="compensation", code="exception",
        display_name="Исключение",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        sort_order=30,
    ),
    dict(
        category="compensation", code="partial_exception",
        display_name="Частичное исключение",
        verification_strategy="manual_only",
        requires_related_debts=True,
        sort_order=40,
    ),
    dict(
        category="compensation", code="no_compensation",
        display_name="Не отработает",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        sort_order=50,
    ),
    dict(
        category="compensation", code="sl",
        display_name="БЛ (больничный)",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        exempts_from_daily_debt=True,
        sort_order=60,
    ),
    dict(
        category="compensation", code="wc",
        display_name="БС",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        exempts_from_daily_debt=True,
        sort_order=70,
    ),
    dict(
        category="compensation", code="study",
        display_name="Учёба",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        exempts_from_daily_debt=True,
        sort_order=80,
    ),
    dict(
        category="compensation", code="vacation",
        display_name="Отпуск",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        exempts_from_daily_debt=True,
        sort_order=90,
    ),
    dict(
        category="compensation", code="retroactive_compensation",
        display_name="Ретроактивная компенсация",
        verification_strategy="retroactive_check",
        allows_past_date=True,
        requires_supervisor_approval=True,
        min_duration=timedelta(minutes=30),
        sort_order=100,
    ),
    # Переносы / отгулы
    dict(
        category="transfer", code="transfer",
        display_name="Перенос рабочего дня",
        verification_strategy="schedule_based",
        requires_date_from=True,
        requires_date_to=True,
        forbidden_on_day_off=True,                # ish kunini dam kunidan ko'chirish mumkin emas
        sort_order=10,
    ),
    dict(
        category="transfer", code="time_off",
        display_name="Отпрашивание",
        verification_strategy="hour_range_based",
        requires_date_from=True,
        requires_date_to=True,
        requires_duration=True,
        exempts_from_daily_debt=True,             # compensation verifier hisobga oladi
        forbidden_on_day_off=True,
        sort_order=20,
    ),
    dict(
        category="transfer", code="training",
        display_name="Обучение",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        requires_duration=True,                   # YANGI: duration majburiy
        exempts_from_daily_debt=True,
        forbidden_on_day_off=True,
        sort_order=30,
    ),
    dict(
        category="transfer", code="vacation",
        display_name="Отпуск",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        exempts_from_daily_debt=True,
        # vacation, sl, wc, study — dam kuniga RUXSAT
        sort_order=40,
    ),
    dict(
        category="transfer", code="sl",
        display_name="БЛ",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        exempts_from_daily_debt=True,
        sort_order=50,
    ),
    dict(
        category="transfer", code="wc",
        display_name="БС",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        exempts_from_daily_debt=True,
        sort_order=60,
    ),
    dict(
        category="transfer", code="study",
        display_name="Учёба",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        exempts_from_daily_debt=True,
        sort_order=70,
    ),
    dict(
        category="transfer", code="office_work",
        display_name="Хозяйственные работы",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        requires_duration=True,                   # YANGI
        exempts_from_daily_debt=True,
        forbidden_on_day_off=True,
        sort_order=80,
    ),
    dict(
        category="transfer", code="benefits",
        display_name="Льгота",
        verification_strategy="date_range_based",
        requires_date_from=True,
        requires_date_to=True,
        requires_duration=True,                   # YANGI
        exempts_from_daily_debt=True,
        forbidden_on_day_off=True,
        sort_order=90,
    ),
    dict(
        category="transfer", code="exception",
        display_name="Исключение",
        verification_strategy="auto_approve",
        auto_approve_on_create=True,
        requires_date_from=True,
        requires_date_to=True,
        requires_duration=True,                   # YANGI
        exempts_from_daily_debt=True,             # YANGI
        forbidden_on_day_off=True,
        sort_order=100,
    ),
]


SYSTEM_POLICIES = [
    dict(
        key="external_api_url",
        value="http://192.168.42.172:5000/csv-to-json/hour_by",
        description="URL внешнего API почасовых логов",
    ),
    dict(
        key="external_api_timeout_seconds",
        value=30,
        description="Таймаут запросов к внешнему API (секунд)",
    ),
    dict(
        key="cycle_close_day",
        value=20,
        description="День месяца для закрытия цикла",
    ),
    dict(
        key="compensation_tolerance_minutes",
        value=5,
        description="Допуск при сравнении плана и факта компенсации (минут)",
    ),
    dict(
        key="allowed_groups",
        value=[
            "1000", "1009", "1093", "1170", "1242",
            "BKM", "INT", "Группа ДОП", "ДОП",
            "Саралаш", "РФ", "Продажа",
            "Нукус 1000", "229 (1000)", "БКМ", "БКМ/09",
            "ДОП 1", "ДОП 2",
        ],
        description="Список разрешённых групп для операций",
    ),
    dict(
        key="google_credential_path",
        value="/home/projects/hour_by_project/creds.json",
        description="Путь к JSON-ключу Google Service Account",
    ),
    dict(
        key="auto_create_operators_from_api",
        value=True,
        description=(
            "Авто-создавать новых операторов, появившихся в API. "
            "True (по умолчанию) — создавать с пустой группой и логировать. "
            "False — игнорировать неизвестные login_id."
        ),
    ),
]


class Command(BaseCommand):
    help = "Первичное наполнение БД базовыми данными"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Удалить существующие записи перед заливкой (ОПАСНО)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Сброс старых данных..."))
            Shift.objects.all().delete()
            RequestTypeRule.objects.all().delete()
            SystemPolicy.objects.all().delete()

        self.stdout.write("Создание смен...")
        for s in SHIFTS:
            (
                code, display_name, start, end, crosses, norm_full,
                norm_lock_soft, norm_lock_warn, tolerance, is_night, special,
            ) = s
            Shift.objects.update_or_create(
                code=code,
                defaults={
                    "display_name": display_name,
                    "start_time": start,
                    "end_time": end,
                    "crosses_midnight": crosses,
                    "norm_full": norm_full,
                    "norm_lock_soft_cap": norm_lock_soft,
                    "norm_lock_warn_at": norm_lock_warn,
                    "tolerance_undertime": tolerance,
                    "is_night": is_night,
                    "requires_special_pipeline": special,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Смены: {len(SHIFTS)}"))

        self.stdout.write("Создание правил заявок...")
        for rule_data in REQUEST_TYPE_RULES:
            RequestTypeRule.objects.update_or_create(
                category=rule_data["category"],
                code=rule_data["code"],
                defaults={**rule_data, "is_active": True},
            )
        self.stdout.write(self.style.SUCCESS(f"Правила заявок: {len(REQUEST_TYPE_RULES)}"))

        self.stdout.write("Создание системных политик...")
        for policy_data in SYSTEM_POLICIES:
            SystemPolicy.objects.update_or_create(
                key=policy_data["key"],
                defaults={
                    "value": policy_data["value"],
                    "description": policy_data["description"],
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Политики: {len(SYSTEM_POLICIES)}"))

        self.stdout.write("Создание активного цикла...")
        cycle = get_or_create_active_cycle()
        self.stdout.write(self.style.SUCCESS(f"Цикл: {cycle}"))

        self.stdout.write(self.style.SUCCESS("Первичное наполнение завершено."))
