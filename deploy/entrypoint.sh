#!/bin/sh
set -e

# Celery-процессы стартуют без миграций и сбора статики
if [ "${1#celery}" != "$1" ]; then
    exec "$@"
fi

python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput || true
fi

exec gunicorn config.asgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --worker-class uvicorn.workers.UvicornWorker \
    --no-control-socket \
    --access-logfile - \
    --error-logfile -
