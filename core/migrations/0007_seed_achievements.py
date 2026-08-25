from django.db import migrations

ACHIEVEMENTS = [
    {'code': 'clicker_100', 'name': 'Разминка', 'description': 'Сделать 100 кликов', 'icon': '👆'},
    {'code': 'clicker_1000', 'name': 'Палец-молоток', 'description': 'Сделать 1000 кликов', 'icon': '🔨'},
    {'code': 'first_trade', 'name': 'Трейдер-новичок', 'description': 'Первая сделка на бирже', 'icon': '📈'},
    {'code': 'ten_trades', 'name': 'Волк с Уолл-стрит', 'description': '10 сделок на бирже', 'icon': '🐺'},
    {'code': 'paper_hands', 'name': 'Бумажные руки', 'description': 'Продать актив в убыток', 'icon': '🧻'},
    {'code': 'diamond_hands', 'name': 'Алмазные руки', 'description': 'Держать позицию при просадке 50%+', 'icon': '💎'},
    {'code': 'millionaire', 'name': 'Миллионер', 'description': 'Капитал 1 000 000 монет', 'icon': '💰'},
]


def seed_achievements(apps, schema_editor):
    Achievement = apps.get_model('core', 'Achievement')
    for data in ACHIEVEMENTS:
        Achievement.objects.update_or_create(code=data['code'], defaults=data)


def remove_achievements(apps, schema_editor):
    Achievement = apps.get_model('core', 'Achievement')
    codes = [a['code'] for a in ACHIEVEMENTS]
    Achievement.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_achievement_marketevent_userachievement'),
    ]

    operations = [
        migrations.RunPython(seed_achievements, remove_achievements),
    ]
