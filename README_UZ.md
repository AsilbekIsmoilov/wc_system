# Python loyihasini Docker + Celery bilan ishga tushirish (deploy to'plami)

Bu papkadagi fayllar Django loyihangizni (`hour_by_project`) konteynerlashtirib, runnerlarni
**Celery Beat** orqali avtomatik ishlatish uchun. Hammasini Django loyiha **root**iga ko'chiring.

## Fayllar va joylashuvi

| Fayl | Joyi | Vazifa |
|------|------|--------|
| `Dockerfile` | root | Django image (mysqlclient + ASGI) |
| `docker-compose.yml` | root | web + worker + beat + redis + mysql |
| `entrypoint.sh` | root | migratsiya + ishga tushirish |
| `init-databases.sql` | root | `project1` + `project1_archive` ni yaratadi |
| `.dockerignore` | root | image ichiga keraksizларни kiritmaydi |
| `.env.example` | root → `.env` | sozlamalar (DB, Redis, token) |
| `gitignore.example` | root → `.gitignore` | git ignore |
| `gitlab-ci.yml.example` | root → `.gitlab-ci.yml` | GitLab CI (build + deploy) |
| `runner_tasks.py` | `hourly_locks/tasks.py` ga **qo'shing** | 3 runner Celery task |
| `celery_beat_schedule.py` | `core/celery.py` ga **merge** | beat jadvali |
| `settings_env_snippet.py` | `core/settings.py` ga **merge** | env asosida sozlama |

## 1. Kodni o'zgartirish (3 joy)

**a) `hourly_locks/tasks.py`** — `runner_tasks.py` ichidagi 3 ta `@shared_task` ni qo'shing.

**b) `core/celery.py`** — yuqorida `from celery.schedules import crontab` qo'shing va
`app.conf.beat_schedule` ni `celery_beat_schedule.py` dagi variant bilan almashtiring.

**c) `core/settings.py`** — `settings_env_snippet.py` dagi env-asosli bloklar bilan
hardcoded `DATABASES`/`CELERY`/`REDIS`/`SECRET_KEY` ni almashtiring (Docker env'dan o'qishi uchun).

## 2. Runner jadvali (Celery Beat)

| Runner | Vaqt | Task |
|--------|------|------|
| daily | har kuni **09:00** | `hourly_locks.run_daily` (kechagi kun) |
| night | har kuni **18:00** | `hourly_locks.run_night` (kechagi kun) |
| monthly | har oy **19-sana 23:30** | `hourly_locks.run_monthly` (cikl yopish) |

Vaqtlar `CELERY_TIMEZONE = 'Asia/Tashkent'` bo'yicha.

> **Diqqat (monthly sana):** task `cycle_service.auto_close_if_due(today)` ni chaqiradi —
> u **muddati kelgan** siklni yopadi. Agar sizning yopilish mantig'ingiz cikl `end_date`
> **o'tgandan keyin** ishlasa (ya'ni 20-sana), `celery_beat_schedule.py` da `day_of_month=19`
> ni **20** ga o'zgartiring. `auto_close_if_due` shartini bir tekshiring (19-da yopadimi yoki 20-da).

## 3. GitHub'ga qo'yish

```bash
cd hour_by_project
git init                       # agar hali git bo'lmasa
cp gitignore.example .gitignore
git add .
git commit -m "chore: dockerize + celery runners"
git remote add origin https://github.com/<user>/<repo>.git
git branch -M main
git push -u origin main
```

> `.env` va `creds.json` ni **commit qilmang** (`.gitignore` da bor). Maxfiy ma'lumotlar
> faqat serverda / CI variables'da bo'lsin.

## 4. Docker bilan ishga tushirish (lokal yoki server)

```bash
cp .env.example .env           # qiymatlarni to'ldiring
docker compose up -d --build
```
Ko'tariladi: `web` (8000), `worker` (celery), `beat` (jadval), `redis`, `db` (mysql).

Tekshirish:
```bash
docker compose ps
docker compose logs -f beat     # jadval yuklanganini ko'rish
docker compose logs -f worker   # task bajarilishini ko'rish
```

> **Eslatma:** `web` konteyneri `RUN_MIGRATIONS=1` bilan migratsiyani bir marta bajaradi.
> `WFM_BASE_URL` — WFM boshqa joyda bo'lsa to'g'ri manzilni qo'ying
> (`host.docker.internal` — host mashinadagi WFM uchun).

## 5. GitLab orqali run (DevOps)

`gitlab-ci.yml.example` ni `.gitlab-ci.yml` deb nomlang. Ikki bosqich:
- **build:** Docker image yasab, GitLab Container Registry'ga push qiladi.
- **deploy:** (manual) serverga SSH bilan kirib `git pull` + `docker compose up -d --build`.

CI/CD Variables (GitLab → Settings → CI/CD → Variables) ga qo'ying:
`DEPLOY_SSH_KEY`, `DEPLOY_USER`, `DEPLOY_HOST` (deploy uchun). Registry login
(`CI_REGISTRY_*`) GitLab tomonidan avtomatik beriladi.

> Eslatma: GitHub'da kod + GitLab'da CI ishlatmoqchi bo'lsangiz, GitLab'da
> "CI/CD for external repository" (GitHub mirror) sozlash kerak. Yoki kodни to'g'ridan-to'g'ri
> GitLab'ga qo'ying — bu eng oson yo'l.

## 6. Tekshirish (runnerlar ishlayaptimi)

```bash
# Qo'lda task'ni darhol chaqirib ko'rish (worker ichida):
docker compose exec worker celery -A core call hourly_locks.run_daily
# yoki Django shell orqali:
docker compose exec web python manage.py shell -c "from hourly_locks.tasks import run_daily_task; run_daily_task.delay()"
```
`worker` loglarida runner bajarilishini va WFM push natijasini ko'rasiz.

## Xulosa

- **3 konteyner:** `web` (API/WS), `worker` (task bajaradi), `beat` (jadval).
- **Runnerlar** Celery task: daily 09:00, night 18:00, monthly 19-sana.
- **Docker** + `.env` bilan har joyda bir xil ishlaydi; **GitLab CI** build/deploy qiladi.
- Maxfiy ma'lumotlar `.env` / CI variables'da — kodda emas.
