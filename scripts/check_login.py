"""Сравнивает ВНЕШНИЙ (10.145.20.9:4020) и ВНУТРЕННИЙ (nginx) путь входа.

Если /api-auth/login/ по внешнему адресу даёт 500, а по внутреннему — 302,
и заголовок Server отличается — значит перед нашим контейнером стоит другой
proxy/бэкенд, и именно он отдаёт 500 (наш стек тут ни при чём).

Запуск: docker compose exec -T web python /tmp/check_login.py
"""
import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0"


def probe(base, host_header=None):
    print(f"--- {base} " + (f"(Host: {host_header}) " if host_header else "") + "---")
    login = base + "/api-auth/login/"
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base_headers = {"Accept": "text/html", "User-Agent": UA}
    if host_header:
        base_headers["Host"] = host_header

    # GET формы
    try:
        resp = op.open(urllib.request.Request(login, headers=dict(base_headers)), timeout=15)
        html = resp.read().decode("utf-8", "replace")
        print("  GET  ->", resp.status, "| Server:", resp.headers.get("Server"))
    except urllib.error.HTTPError as e:
        html = e.read().decode("utf-8", "replace")
        print("  GET  -> HTTP", e.code, "| Server:", e.headers.get("Server"))
    except Exception as e:  # noqa: BLE001
        print("  GET  -> СЕТЬ:", repr(e))
        return
    m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
    token = m.group(1) if m else ""

    # POST входа
    data = urllib.parse.urlencode({
        "username": "admin", "password": "123",
        "csrfmiddlewaretoken": token, "next": "/api/v1/",
    }).encode()
    headers = dict(base_headers)
    origin = base if not host_header else "http://" + host_header
    headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin,
        "Referer": origin + "/api-auth/login/",
    })
    try:
        resp = op.open(urllib.request.Request(login, data=data, headers=headers, method="POST"), timeout=15)
        print("  POST ->", resp.status, "| Server:", resp.headers.get("Server"), "(500 НЕТ)")
    except urllib.error.HTTPError as e:
        print("  POST -> HTTP", e.code, "| Server:", e.headers.get("Server"))
        print("       via:", e.headers.get("Via"), "| X-Powered-By:", e.headers.get("X-Powered-By"))
    except Exception as e:  # noqa: BLE001
        print("  POST -> СЕТЬ:", repr(e))


# 1) Внешний реальный адрес (как браузер)
probe("http://10.145.20.9:4020")
# 2) Наш внутренний nginx напрямую
probe("http://nginx", host_header="10.145.20.9:4020")
