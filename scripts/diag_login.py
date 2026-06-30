"""ВРЕМЕННАЯ диагностика 500 при логине — имитация РЕАЛЬНОГО браузера через nginx.

Полный набор браузерных заголовков + предварительный заход на /api/v1/ (cookies),
затем логин формой admin. Печатает тело при 500 (DEBUG=1 => traceback).
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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BROWSER = {
    "Host": HOST,
    "User-Agent": UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8"),
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}


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


def get(opener, path, extra=None):
    h = dict(BROWSER)
    if extra:
        h.update(extra)
    try:
        return opener.open(urllib.request.Request(BASE + path, headers=h), timeout=25)
    except urllib.error.HTTPError as e:
        return e


_wait()
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# как браузер: сперва заходим на /api/v1/, потом на форму логина
show("[GET /api/v1/]", get(op, "/api/v1/"))
g = get(op, "/admin/login/?next=/admin/")
show("[GET /admin/login/]", g)
html = g.read().decode("utf-8", "ignore") if not isinstance(g, urllib.error.HTTPError) else ""
m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
form = urllib.parse.urlencode({
    "username": "admin", "password": "123",
    "csrfmiddlewaretoken": m.group(1) if m else "", "next": "/admin/",
}).encode()
post_headers = dict(BROWSER)
post_headers.update({
    "Origin": ORIGIN, "Referer": BASE + "/admin/login/?next=/admin/",
    "Content-Type": "application/x-www-form-urlencoded",
    "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate",
})
try:
    r = op.open(urllib.request.Request(
        BASE + "/admin/login/?next=/admin/", data=form, headers=post_headers), timeout=25)
    show("[POST /admin/login/]", r)
except urllib.error.HTTPError as e:
    show("[POST /admin/login/]", e)

show("[GET /admin/ после]", get(op, "/admin/"))
