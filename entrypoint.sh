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
fi

exec "$@"
