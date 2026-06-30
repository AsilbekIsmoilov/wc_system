"""ВРЕМЕННАЯ диагностика 500 при логине/после логина — РЕАЛЬНЫЙ HTTP через nginx.

Логинится формой admin (с Origin, как браузер), затем запрашивает страницы
ПОСЛЕ логина (/admin/ index, /api/v1/, me) и печатает тело при 500 (DEBUG=1).
"""
import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "10.145.20.9:4020"
ORIGIN = "http://10.145.20.9:4020"
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


def show(label, r):
    if isinstance(r, urllib.error.HTTPError):
        print(label, "STATUS", r.code)
        print("---- BODY ----")
        print(r.read().decode("utf-8", "ignore")[:9000])
    else:
        print(label, "STATUS", r.getcode())


def login_admin():
    """GET /admin/login/ -> POST (с Origin). Возвращает authenticated opener."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    url = BASE + "/admin/login/?next=/admin/"
    g = opener.open(urllib.request.Request(url, headers={"Host": HOST}), timeout=25)
    html = g.read().decode("utf-8", "ignore")
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    form = urllib.parse.urlencode({
        "username": "admin", "password": "123",
        "csrfmiddlewaretoken": m.group(1) if m else "", "next": "/admin/",
    }).encode()
    resp = opener.open(urllib.request.Request(
        url, data=form,
        headers={"Host": HOST, "Origin": ORIGIN, "Referer": url,
                 "Content-Type": "application/x-www-form-urlencoded"},
    ), timeout=25)
    print("[login POST/redirect] STATUS", resp.getcode(), "url:", resp.geturl())
    return opener


_wait()
print("=== ЛОГИН + СТРАНИЦЫ ПОСЛЕ ЛОГИНА ===")
try:
    op = login_admin()
    for p in ["/admin/", "/api/v1/", "/api/v1/auth/me/"]:
        try:
            show("[GET " + p + "]", op.open(
                urllib.request.Request(BASE + p, headers={"Host": HOST, "Accept": "text/html"}),
                timeout=25))
        except urllib.error.HTTPError as e:
            show("[GET " + p + "]", e)
        except Exception as e:  # noqa: BLE001
            print("[GET", p, "] ERR", repr(e))
except urllib.error.HTTPError as e:
    show("[login]", e)
except Exception as e:  # noqa: BLE001
    print("[login] ERR", repr(e))
