from django.db import migrations

SEED_ASSETS = [
    {
        'ticker': 'STBL',
        'name': 'СтейблКоин Индастриз',
        'mu': 0.00001,
        'sigma': 0.0025,
        'price': 100.0,
    },
]


def seed_assets(apps, schema_editor):
    from django.utils import timezone

    Asset = apps.get_model('core', 'Asset')
    for data in SEED_ASSETS:
        Asset.objects.update_or_create(
            ticker=data['ticker'],
            defaults={**data, 'last_tick_at': timezone.now()},
        )


def remove_assets(apps, schema_editor):
    Asset = apps.get_model('core', 'Asset')
    tickers = [a['ticker'] for a in SEED_ASSETS]
    Asset.objects.filter(ticker__in=tickers).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_asset_pricetick_transaction_holding'),
    ]

    operations = [
        migrations.RunPython(seed_assets, remove_assets),
    ]
