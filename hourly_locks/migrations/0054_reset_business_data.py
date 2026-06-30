"""
НЕЙТРАЛИЗОВАНА. (Ранее — одноразовый сброс бизнес-данных.)

Логика очистки БД удалена по требованию. Файл оставлен ПУСТЫМ (без операций),
а НЕ удалён, потому что миграция могла быть уже применена (на проде и/или
локально) — удаление записи из истории миграций сломало бы её целостность и
привело бы к коллизии номера 0054 при будущих makemigrations.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0053_alter_workdebtdetail_source_uchebaday"),
    ]

    operations = []
