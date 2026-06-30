# Data migration: seed RequestTypeRule for both categories (compensation + transfer)
from django.db import migrations


# (code, display_name, group)  group: "work" | "benefit"
TYPES = [
    ("otrabotka",        "Отработка",                        "work"),
    ("otprashivanie",    "Отпрашивание",                     "work"),
    ("isklyuchenie",     "Исключение",                       "benefit"),
    ("ne_otrabotaet",    "Не отработает",                    "benefit"),
    ("ucheba_rabochee",  "Учёба в рабочее время",            "benefit"),
    ("perenos_dnya",     "Перенос рабочего дня",             "work"),
    ("obuchenie",        "Обучение",                         "benefit"),
    ("lgota",            "Льгота",                           "benefit"),
    ("lgota_brak",       "Льгота по бракосочетанию",         "benefit"),
    ("lgota_rojdenie",   "Льгота по рождению ребёнка",       "benefit"),
    ("lgota_utrata",     "Льгота по утрате родственника",    "benefit"),
    ("lgota_pereezd",    "Льгота по переезду",               "benefit"),
    ("lgota_prochie",    "Прочие льготы",                    "benefit"),
    ("hoz_raboty",       "Хозяйственные работы",             "benefit"),
]

CATEGORIES = ["compensation", "transfer"]


def seed(apps, schema_editor):
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    for category in CATEGORIES:
        for idx, (code, display_name, group) in enumerate(TYPES, start=1):
            if group == "benefit":
                flags = {
                    "creates_debt_if_unmet": False,
                    "exempts_from_daily_debt": True,
                    "auto_approve_on_create": True,
                    "allows_past_date": True,
                    "verification_strategy": "auto_approve",
                }
            else:  # work
                flags = {
                    "creates_debt_if_unmet": True,
                    "exempts_from_daily_debt": False,
                    "auto_approve_on_create": False,
                    "allows_past_date": False,
                    "verification_strategy": "schedule_based",
                }
            RequestTypeRule.objects.update_or_create(
                category=category,
                code=code,
                defaults={
                    "display_name": display_name,
                    "sort_order": idx * 10,
                    "is_active": True,
                    **flags,
                },
            )


def unseed(apps, schema_editor):
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    codes = [c for c, _, _ in TYPES]
    RequestTypeRule.objects.filter(
        category__in=CATEGORIES, code__in=codes
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0041_remove_operator_photo"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
