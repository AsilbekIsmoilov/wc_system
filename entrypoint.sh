#!/usr/bin/env sh
set -e

if [ "${RUN_MIGRATIONS}" = "1" ]; then
  echo "Migrating default DB..."
  python manage.py migrate --noinput
  echo "Migrating archive DB..."
  python manage.py migrate --database=archive --noinput
  echo "Collecting static..."
  python manage.py collectstatic --noinput
  echo "Ensuring superuser (admin/123)..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(username='admin').exists() or U.objects.create_superuser('admin','','123')"

  ( echo "daily_runner 1/2..."; python daily_runner.py; \
    echo "daily_runner 2/2..."; python daily_runner.py ) &
fi

exec "$@"