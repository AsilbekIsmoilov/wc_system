from django.db import migrations


def remove_transfer_ne_otrabotaet(apps, schema_editor):
    """Удалить тип «Не отработает» (ne_otrabotaet) из категории transfer.
    Остаётся только в compensation. Удаляется лишь если не используется."""
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    Transfer = apps.get_model("hourly_locks", "Transfer")
    rule = RequestTypeRule.objects.filter(
        category="transfer", code="ne_otrabotaet",
    ).first()
    if not rule:
        return
    if Transfer.objects.filter(type_rule=rule).exists():
        # есть ссылки (PROTECT) — не удаляем, лишь деактивируем
        rule.is_active = False
        rule.save(update_fields=["is_active"])
    else:
        rule.delete()


def restore_transfer_ne_otrabotaet(apps, schema_editor):
    """Откат: вернуть тип в transfer (benefit-флаги)."""
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    RequestTypeRule.objects.update_or_create(
        category="transfer", code="ne_otrabotaet",
        defaults=dict(
            display_name="Не отработает",
            verification_strategy="auto_approve",
            creates_debt_if_unmet=False,
            exempts_from_daily_debt=True,
            auto_approve_on_create=True,
            allows_past_date=True,
            is_active=True,
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0047_alter_workdebtdetail_source"),
    ]

    operations = [
        migrations.RunPython(
            remove_transfer_ne_otrabotaet,
            restore_transfer_ne_otrabotaet,
        ),
    ]
