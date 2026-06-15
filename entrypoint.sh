#!/bin/sh
set -e

echo "Waiting for MySQL at ${DB_HOST}:${DB_PORT:-3306}..."
while ! nc -z "${DB_HOST}" "${DB_PORT:-3306}"; do
  sleep 1
done
echo "MySQL is up."

# Migrations only on the web container (avoid running 3x). Set RUN_MIGRATIONS=1 there.
if [ "${RUN_MIGRATIONS}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput || true
fi

exec "$@"
