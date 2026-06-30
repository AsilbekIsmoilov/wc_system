"""ВРЕМЕННАЯ диагностика 500 на /api/v1/ (запрос напрямую к uvicorn).

Ждёт пока uvicorn поднимется (retry на ConnectionRefused), затем печатает
статус и тело ответа. При DEBUG=1 тело 500 содержит полный traceback.
Запуск из CI: `docker compose exec -T web python scripts/diag500.py`.
"""
import os
import time
import urllib.error
import urllib.request

print("=== ENV DEBUG =", os.environ.get("DEBUG"), "===")

URL = "http://localhost:8000/api/v1/"

for attempt in range(40):
    try:
        req = urllib.request.Request(URL, headers={"Accept": "text/html"})
        resp = urllib.request.urlopen(req, timeout=25)
        print("STATUS", resp.getcode(), "(OK, не 500)")
        break
    except urllib.error.HTTPError as exc:
        print("STATUS", exc.code)
        print("---- RESPONSE BODY (first 9000) ----")
        print(exc.read().decode("utf-8", "ignore")[:9000])
        break
    except urllib.error.URLError:
        # uvicorn ещё не слушает порт — ждём и пробуем снова
        time.sleep(2)
    except Exception as exc:  # noqa: BLE001
        print("ERR", repr(exc))
        break
else:
    print("uvicorn не поднялся за ~80с — порт 8000 не отвечает")
