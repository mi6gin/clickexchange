from django.core.management.base import BaseCommand

from core import generator
from core.models import Asset


class Command(BaseCommand):
    help = 'Вывести N новых компаний на биржу (IPO)'

    def add_arguments(self, parser):
        parser.add_argument('count', nargs='?', type=int, default=1)

    def handle(self, *args, **options):
        count = options['count']
        room = generator.MAX_ASSETS - Asset.objects.count()
        created = 0

        for _ in range(min(count, max(room, 0))):
            asset = generator.generate_company()
            self.stdout.write(
                self.style.SUCCESS(
                    f'IPO: {asset.ticker} — {asset.name} '
                    f'@ {asset.price} (σ={asset.sigma:.4f})',
                ),
            )
            created += 1

        if created < count:
            self.stdout.write(
                f'Создано {created} из {count}: на бирже нет мест '
                f'(лимит {generator.MAX_ASSETS}).',
            )
