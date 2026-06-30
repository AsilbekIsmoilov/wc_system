"""ВРЕМЕННАЯ диагностика 500 при логине — РЕАЛЬНЫЙ HTTP через nginx.

Пробует 3 способа входа (token / admin-форма / browsable API) и печатает статус
и тело (при DEBUG=1 тело 500 = traceback). Запуск из CI:
    docker compose exec -T web python scripts/diag_login.py
"""
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "10.145.20.9:4020"
BASE = "http://nginx"


def _wait():
    for _ in range(40):
        try:
            urllib.request.urlopen("http://localhost:8000/api/v1/", timeout=10)
            return
        except urllib.error.HTTPError:
            return
        except urllib.error.URLError:
            time.sleep(2)


def show(label, resp_or_exc):
    if isinstance(resp_or_exc, urllib.error.HTTPError):
        print(label, "STATUS", resp_or_exc.code)
        print("---- BODY ----")
        print(resp_or_exc.read().decode("utf-8", "ignore")[:9000])
    else:
        print(label, "STATUS", resp_or_exc.getcode())


def form_login(path):
    """GET страницы (csrf) -> POST формы через nginx."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    url = BASE + path
    g = opener.open(urllib.request.Request(url, headers={"Host": HOST}), timeout=25)
    html = g.read().decode("utf-8", "ignore")
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    form = urllib.parse.urlencode({
        "username": "admin", "password": "123",
        "csrfmiddlewaretoken": csrf, "next": "/api/v1/",
    }).encode()
    return opener.open(urllib.request.Request(
        url, data=form,
        headers={"Host": HOST, "Referer": url,
                 "Content-Type": "application/x-www-form-urlencoded"},
    ), timeout=25)


_wait()

# [1] JWT token
print("=== [1] POST /api/v1/auth/token/ ===")
try:
    body = json.dumps({"username": "admin", "password": "123"}).encode()
    show("[token]", urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/v1/auth/token/", data=body,
        headers={"Content-Type": "application/json", "Host": HOST}), timeout=25))
except urllib.error.HTTPError as e:
    show("[token]", e)
except Exception as e:  # noqa: BLE001
    print("[token] ERR", repr(e))

# [2] admin-форма
print("=== [2] POST /admin/login/ ===")
try:
    show("[admin]", form_login("/admin/login/?next=/admin/"))
except urllib.error.HTTPError as e:
    show("[admin]", e)
except Exception as e:  # noqa: BLE001
    print("[admin] ERR", repr(e))

# [3] browsable API login
print("=== [3] POST /api-auth/login/ ===")
try:
    show("[api-auth]", form_login("/api-auth/login/?next=/api/v1/"))
except urllib.error.HTTPError as e:
    show("[api-auth]", e)
except Exception as e:  # noqa: BLE001
    print("[api-auth] ERR", repr(e))
