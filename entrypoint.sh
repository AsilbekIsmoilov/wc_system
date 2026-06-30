#!/bin/sh
set -e

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "[entrypoint] Applying migrations (default)..."
  python manage.py migrate --noinput
  echo "[entrypoint] Applying migrations (archive)..."
  python manage.py migrate --database=archive --noinput

  echo "[entrypoint] Seeding initial data (idempotent)..."
  python manage.py seed_initial_data

  echo "[entrypoint] Collecting static files..."
  python manage.py collectstatic --noinput

  echo "[entrypoint] Ensuring admin superuser..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; U = get_user_model(); u, created = U.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True, 'role': 'admin'}); (u.set_password('123'), u.save(), print('[entrypoint] superuser admin created')) if created else print('[entrypoint] superuser admin already exists')"
fi

exec "$@"
