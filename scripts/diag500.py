"""ВРЕМЕННАЯ диагностика 500 на /api/v1/ (запрос напрямую к uvicorn).

Печатает: значение env DEBUG в контейнере, статус ответа и тело (при DEBUG=1 —
полный traceback). Запускается из CI: `docker compose exec -T web python scripts/diag500.py`.
"""
import os
import urllib.error
import urllib.request

print("=== ENV DEBUG =", os.environ.get("DEBUG"), "===")

req = urllib.request.Request(
    "http://localhost:8000/api/v1/",
    headers={"Accept": "text/html"},
)
try:
    resp = urllib.request.urlopen(req, timeout=25)
    print("STATUS", resp.getcode())
except urllib.error.HTTPError as exc:
    print("STATUS", exc.code)
    body = exc.read().decode("utf-8", "ignore")
    print("---- RESPONSE BODY (first 6000) ----")
    print(body[:6000])
except Exception as exc:  # noqa: BLE001
    print("ERR", repr(exc))
