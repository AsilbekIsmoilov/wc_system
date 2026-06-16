#!/bin/sh
set -e

echo "Waiting for MySQL at ${DB_HOST}:${DB_PORT:-3306}..."
while ! nc -z "${DB_HOST}" "${DB_PORT:-3306}"; do
  sleep 1
done
echo "MySQL is up."

if [ "${RUN_MIGRATIONS}" = "1" ]; then
  echo "Running migrations (default)..."
  python manage.py migrate --noinput

  echo "Running migrations (archive)..."
  python manage.py migrate --database=archive --noinput

  python manage.py collectstatic --noinput || true

  echo "Seeding initial data..."
  python manage.py seed_initial_data || echo "seed_initial_data: skipped/failed"

  echo "Ensuring superuser (admin)..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(username='admin').exists() or U.objects.create_superuser(username='admin', email='admin@example.com', password='123')" || true
fi

exec "$@"