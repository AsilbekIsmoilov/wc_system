set -e

if [ "${RUN_MIGRATIONS}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py migrate --database=archive --noinput
  python manage.py collectstatic --noinput
  python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(username='admin').exists() or U.objects.create_superuser('admin','','123')"

  ( python daily_runner.py || echo 'daily_runner 1 failed' ) &
fi

exec "$@"