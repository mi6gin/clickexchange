"""
Настройки продакшена: PostgreSQL, Redis-кэш, HTTPS/HSTS.

Все секреты приходят через переменные окружения (см. .env.example).
Запускается автоматически при DJANGO_ENV=production (см. __init__.py).
"""

import os

from .base import *  # noqa: F401,F403

DEBUG = False

try:
    SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
except KeyError as exc:
    raise RuntimeError(
        'Переменная DJANGO_SECRET_KEY не задана. '
        'Сгенерируйте: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"',
    ) from exc

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]
if not ALLOWED_HOSTS:
    raise RuntimeError('Переменная ALLOWED_HOSTS не задана (пример: localhost,example.com)')

CSRF_TRUSTED_ORIGINS = [
    origin for origin in (
        f"https://{host}" for host in ALLOWED_HOSTS
    )
]

# --- PostgreSQL ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'clickexchange'),
        'USER': os.environ.get('POSTGRES_USER', 'clicker'),
        'PASSWORD': os.environ['POSTGRES_PASSWORD'],
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_HEALTH_CHECKS': True,
    }
}

# --- Redis: кэш (axes корректно считает попытки между воркерами gunicorn) ---
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# --- HTTPS / HSTS / cookies ---
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 год
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
