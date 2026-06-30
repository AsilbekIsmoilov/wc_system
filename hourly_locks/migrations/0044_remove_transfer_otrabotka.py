# Data migration: отработка нужна только в Compensation.
# Удаляем тип "otrabotka" из категории transfer (на него не ссылается ни одна заявка).
from django.db import migrations


def remove(apps, schema_editor):
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    Transfer = apps.get_model("hourly_locks", "Transfer")

    qs = RequestTypeRule.objects.filter(category="transfer", code="otrabotka")
    # Не удаляем, если вдруг есть ссылающиеся заявки (PROTECT) — оставим неактивным.
    for rule in qs:
        if Transfer.objects.filter(type_rule=rule).exists():
            rule.is_active = False
            rule.save(update_fields=["is_active"])
        else:
            rule.delete()


def restore(apps, schema_editor):
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    RequestTypeRule.objects.update_or_create(
        category="transfer", code="otrabotka",
        defaults={
            "display_name": "Отработка",
            "sort_order": 10,
            "is_active": True,
            "creates_debt_if_unmet": True,
            "exempts_from_daily_debt": False,
            "auto_approve_on_create": False,
            "allows_past_date": False,
            "verification_strategy": "schedule_based",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0043_compensationday"),
    ]

    operations = [
        migrations.RunPython(remove, restore),
    ]
