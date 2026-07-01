"""Диагностика: к какой БД подключено приложение + тест логина на РЕАЛЬНОЙ БД.

Запуск: docker compose exec -T web python scripts/diag_conn.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.db import connections  # noqa: E402

d = connections["default"].settings_dict
a = connections["archive"].settings_dict
print("=== К каким БД подключено приложение ===")
print("  ENV DB_NAME         =", os.environ.get("DB_NAME"))
print("  ENV DB_NAME_ARCHIVE =", os.environ.get("DB_NAME_ARCHIVE"))
print("  DEFAULT ->", d["NAME"], "@", d["HOST"] + ":" + str(d["PORT"]))
print("  ARCHIVE ->", a["NAME"], "@", a["HOST"] + ":" + str(a["PORT"]))

# сколько таблиц реально в default БД
try:
    tbls = connections["default"].introspection.table_names()
    print("  таблиц в DEFAULT БД:", len(tbls), "| django_session:", "django_session" in tbls)
except Exception as exc:  # noqa: BLE001
    print("  ошибка чтения таблиц:", repr(exc))

print("=== ТЕСТ ЛОГИНА на РЕАЛЬНОЙ БД (admin/123) ===")
from django.test import Client  # noqa: E402
try:
    c = Client()
    print("  login(admin/123):", c.login(username="admin", password="123"))
    print("  GET /admin/:", c.get("/admin/").status_code)
    print("  GET /api/v1/auth/me/:", c.get("/api/v1/auth/me/").status_code)
    print("  POST /api/v1/auth/token/:", Client().post(
        "/api/v1/auth/token/",
        '{"username":"admin","password":"123"}',
        content_type="application/json").status_code)
except Exception:
    print("  !!! ОШИБКА (traceback ниже) !!!")
    traceback.print_exc()
