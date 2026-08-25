import time

from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = 'Ждёт готовности базы данных (нужно в docker-compose)'

    def add_arguments(self, parser):
        parser.add_argument('--max-retries', type=int, default=30)
        parser.add_argument('--sleep', type=float, default=1.0)

    def handle(self, *args, **options):
        max_retries = options['max_retries']
        sleep = options['sleep']

        for attempt in range(1, max_retries + 1):
            try:
                connection = connections['default']
                connection.ensure_connection()
            except Exception as exc:
                self.stdout.write(
                    f'[{attempt}/{max_retries}] БД недоступна ({exc.__class__.__name__}), ждём {sleep}с...',
                )
                time.sleep(sleep)
            else:
                self.stdout.write(self.style.SUCCESS('БД готова!'))
                return

        raise RuntimeError(f'БД не стала доступна за {max_retries} попыток')
