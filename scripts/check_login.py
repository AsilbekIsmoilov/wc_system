"""Воспроизводит вход /api-auth/login/ ТОЧНО как браузер, на уровне заголовков.

Подключается к внутреннему nginx, но шлёт Host/Origin/Referer = внешний
адрес (http://10.145.20.9:4020) и Accept: text/html — то есть Django видит
ровно тот же запрос, что и из браузера. Так ловим 500, зависящий от
Host/Origin/Accept, не завися от сетевой доступности внешнего IP.

Запуск: docker compose exec -T web python scripts/check_login.py
"""
import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request

# Коннектимся ПО СЕТИ на реальный внешний адрес (как браузер), чтобы пройти
# через всё, что стоит перед контейнером (host-nginx/прокси), а не только
# внутренний nginx.
EXT = "http://10.145.20.9:4020"
LOGIN = EXT + "/api-auth/login/"
UA = "Mozilla/5.0"
BROWSER_HEADERS = {
    "Accept": "text/html",
    "User-Agent": UA,
}

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# 1) GET формы логина
g = urllib.request.Request(LOGIN, headers=dict(BROWSER_HEADERS))
try:
    html = op.open(g, timeout=15).read().decode("utf-8", "replace")
except urllib.error.HTTPError as e:
    html = e.read().decode("utf-8", "replace")
    print("  GET /api-auth/login/ -> HTTP", e.code)
m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
token = m.group(1) if m else ""
print("  csrfmiddlewaretoken:", "FOUND" if token else "MISSING")

# 2) POST логина ровно как браузер
data = urllib.parse.urlencode({
    "username": "admin",
    "password": "123",
    "csrfmiddlewaretoken": token,
    "next": "/api/v1/",
}).encode()
headers = dict(BROWSER_HEADERS)
headers.update({
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": EXT,
    "Referer": EXT + "/api-auth/login/",
})
req = urllib.request.Request(LOGIN, data=data, headers=headers, method="POST")
try:
    r = op.open(req, timeout=15)
    print("  POST /api-auth/login/ ->", r.status, "(вход отработал, 500 НЕТ)")
    print("  body:", r.read()[:200].decode("utf-8", "replace"))
except urllib.error.HTTPError as e:
    print("  POST /api-auth/login/ -> HTTP", e.code, "(вот она, ошибка)")
    print("  body:", e.read()[:600].decode("utf-8", "replace"))
except Exception as e:  # noqa: BLE001
    print("  ОШИБКА (сеть):", repr(e))
