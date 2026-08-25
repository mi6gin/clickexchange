from django.db import migrations

MORE_ASSETS = [
    {'ticker': 'BANK', 'name': 'Банк Банкович и сыновья', 'mu': 0.00003, 'sigma': 0.004, 'price': 250.0},
    {'ticker': 'GLMN', 'name': 'Гильмон Групп', 'mu': 0.00005, 'sigma': 0.007, 'price': 77.0},
    {'ticker': 'MEME', 'name': 'МемИндустриз Холдинг', 'mu': 0.00008, 'sigma': 0.013, 'price': 42.0},
    {'ticker': 'DOGE2', 'name': 'КриптоПёс Тудей', 'mu': 0.0001, 'sigma': 0.02, 'price': 0.5},
]


def seed_assets(apps, schema_editor):
    from django.utils import timezone

    Asset = apps.get_model('core', 'Asset')
    for data in MORE_ASSETS:
        Asset.objects.update_or_create(
            ticker=data['ticker'],
            defaults={**data, 'last_tick_at': timezone.now()},
        )


def remove_assets(apps, schema_editor):
    Asset = apps.get_model('core', 'Asset')
    tickers = [a['ticker'] for a in MORE_ASSETS]
    Asset.objects.filter(ticker__in=tickers).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_seed_assets'),
    ]

    operations = [
        migrations.RunPython(seed_assets, remove_assets),
    ]
