"""Настройки локальной разработки: SQLite, DEBUG=True."""

from .base import *  # noqa: F401,F403

DEBUG = True

SECRET_KEY = 'django-insecure-e&=q=mem=!$k2^gjoj10$3uwaoaq)n!q_%q_@ct83n3u1%k1p4'

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
