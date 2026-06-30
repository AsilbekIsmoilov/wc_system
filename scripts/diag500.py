"""ВРЕМЕННАЯ диагностика 500 на /api/v1/.

Ждёт uvicorn, затем дёргает /api/v1/ двумя путями:
  1) напрямую к uvicorn (web:8000)
  2) через nginx (как браузер, с Host реального хоста)
Печатает статус и тело (при DEBUG=1 тело 500 = полный traceback).
"""
import os
import time
import urllib.error
import urllib.request

print("=== ENV DEBUG =", os.environ.get("DEBUG"), "===")


def hit(label, url, host=None):
    headers = {"Accept": "text/html"}
    if host:
        headers["Host"] = host
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=25
        )
        print(label, "STATUS", r.getcode())
    except urllib.error.HTTPError as exc:
        print(label, "STATUS", exc.code)
        print("---- BODY (first 9000) ----")
        print(exc.read().decode("utf-8", "ignore")[:9000])
    except Exception as exc:  # noqa: BLE001
        print(label, "ERR", repr(exc))


# ждём, пока uvicorn начнёт слушать порт
for _ in range(40):
    try:
        urllib.request.urlopen("http://localhost:8000/api/v1/", timeout=10)
        break
    except urllib.error.HTTPError:
        break
    except urllib.error.URLError:
        time.sleep(2)

hit("[DIRECT uvicorn]", "http://localhost:8000/api/v1/")
hit("[VIA nginx]", "http://nginx/api/v1/", host="10.145.20.9:4020")
