from django.db import migrations


def set_ucheba_flags(apps, schema_editor):
    """Учёба в рабочее время: НЕ освобождает от долга (норма не уменьшается),
    проверяется по факту (services.ucheba), может создавать долг."""
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    RequestTypeRule.objects.filter(code="ucheba_rabochee").update(
        exempts_from_daily_debt=False,
        creates_debt_if_unmet=True,
        auto_approve_on_create=False,
        verification_strategy="schedule_based",
    )


def revert_ucheba_flags(apps, schema_editor):
    RequestTypeRule = apps.get_model("hourly_locks", "RequestTypeRule")
    RequestTypeRule.objects.filter(code="ucheba_rabochee").update(
        exempts_from_daily_debt=True,
        creates_debt_if_unmet=False,
        auto_approve_on_create=True,
        verification_strategy="auto_approve",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0051_benefitday"),
    ]

    operations = [
        migrations.RunPython(set_ucheba_flags, revert_ucheba_flags),
    ]
