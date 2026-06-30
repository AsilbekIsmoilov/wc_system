"""
ОДНОРАЗОВЫЙ сброс бизнес-данных (для прода без доступа к серверу).

Выполняется ОДИН раз при `migrate` (запись в django_migrations гарантирует,
что повтора не будет — в отличие от env-флага). НЕ зависит от RESET_DB и любых
переопределений окружения на проде.

Удаляет ВСЕ бизнес-данные (операторы, графики, логи, долги, компенсации,
переносы, циклы, события и т.п. + attendance + архив). СОХРАНЯЕТ конфигурацию,
чтобы приложение осталось рабочим даже без повторного seed:
  - hourly_locks_user            (учётки персонала / админ)
  - hourly_locks_shift           (смены)
  - hourly_locks_requesttyperule (типы заявок)
  - hourly_locks_systempolicy    (системные политики)

На пустой/новой БД (dev) — удаляет из пустых таблиц, т.е. безвреден.
"""
from django.db import migrations, connections

KEEP = {
    "hourly_locks_user",
    "hourly_locks_shift",
    "hourly_locks_requesttyperule",
    "hourly_locks_systempolicy",
}


def _wipe(cursor, prefixes, keep):
    cursor.execute("SET FOREIGN_KEY_CHECKS=0")
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    wiped = []
    for t in tables:
        if t in keep:
            continue
        if any(t.startswith(p) for p in prefixes):
            cursor.execute("DELETE FROM `%s`" % t)
            wiped.append(t)
    cursor.execute("SET FOREIGN_KEY_CHECKS=1")
    return wiped


def reset_data(apps, schema_editor):
    # Только на default БД (миграции hourly_locks применяются к default).
    if schema_editor.connection.alias != "default":
        return

    with schema_editor.connection.cursor() as cur:
        wiped = _wipe(cur, ("hourly_locks_", "attendance_"), KEEP)
    print("[migration 0054] default БД очищена, таблиц: %d" % len(wiped))

    # Архивная БД — все archive_* таблицы.
    try:
        arch = connections["archive"]
        with arch.cursor() as cur:
            wiped_a = _wipe(cur, ("archive_",), set())
        print("[migration 0054] archive БД очищена, таблиц: %d" % len(wiped_a))
    except Exception as exc:  # архивной БД может не быть в каких-то окружениях
        print("[migration 0054] archive БД пропущена: %s" % exc)


def noop(apps, schema_editor):
    # Необратимо (данные не восстановить); откат — пустая операция.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hourly_locks", "0053_alter_workdebtdetail_source_uchebaday"),
    ]

    operations = [
        migrations.RunPython(reset_data, noop),
    ]
