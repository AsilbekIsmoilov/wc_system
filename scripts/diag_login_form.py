"""Воспроизводит РОВНО браузерный вход через DRF browsable-API форму:
GET /api-auth/login/ (берём csrftoken) -> POST с логином/паролем/CSRF.
Именно этот путь даёт 500 в браузере (в отличие от JWT /api/v1/auth/token/).

Бьёт по сервису nginx изнутри сети compose. После этого шага в логах web
появится traceback (его пишет логгер django.request на уровне ERROR).

Запуск: docker compose exec -T web python scripts/diag_login_form.py
"""
import http.cookiejar
import re
import urllib.parse
import urllib.request

BASE = "http://nginx"
LOGIN = BASE + "/api-auth/login/"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def show(tag, resp_or_err, body):
    print(f"  [{tag}] status={getattr(resp_or_err, 'status', getattr(resp_or_err, 'code', '?'))}")
    print(f"        body: {body[:600]}")


# 1) GET формы логина -> получаем csrftoken (cookie) и csrfmiddlewaretoken (в HTML)
req = urllib.request.Request(LOGIN, method="GET")
with opener.open(req, timeout=15) as resp:
    html = resp.read().decode("utf-8", "replace")
m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
token = m.group(1) if m else ""
cookies = "; ".join(f"{c.name}={c.value}" for c in jar)
print(f"  GET /api-auth/login/ -> csrfmiddlewaretoken={'FOUND' if token else 'MISSING'} | cookies={cookies}")

# 2) POST логина ровно как браузер
data = urllib.parse.urlencode({
    "username": "admin",
    "password": "123",
    "csrfmiddlewaretoken": token,
    "next": "/api/v1/",
}).encode()
headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": LOGIN,
}
req = urllib.request.Request(LOGIN, data=data, headers=headers, method="POST")
try:
    with opener.open(req, timeout=15) as resp:
        show("POST OK", resp, resp.read().decode("utf-8", "replace"))
except urllib.error.HTTPError as e:
    show("POST HTTPError", e, e.read().decode("utf-8", "replace"))
except Exception as exc:  # noqa: BLE001
    print(f"  POST -> СЕТЕВАЯ ОШИБКА: {exc!r}")
