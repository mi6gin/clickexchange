from django.db import migrations

UPGRADES = [
    {'kind': 'click_power', 'base_cost': 50, 'cost_multiplier': 1.6, 'effect_per_level': 1.0},
    {'kind': 'crit_chance', 'base_cost': 150, 'cost_multiplier': 1.8, 'effect_per_level': 0.02},
    {'kind': 'auto_clicker', 'base_cost': 200, 'cost_multiplier': 1.7, 'effect_per_level': 0.5},
    {'kind': 'max_energy', 'base_cost': 300, 'cost_multiplier': 2.0, 'effect_per_level': 25.0},
]


def seed_upgrades(apps, schema_editor):
    Upgrade = apps.get_model('core', 'Upgrade')
    for data in UPGRADES:
        Upgrade.objects.update_or_create(kind=data['kind'], defaults=data)


def remove_upgrades(apps, schema_editor):
    Upgrade = apps.get_model('core', 'Upgrade')
    kinds = [data['kind'] for data in UPGRADES]
    Upgrade.objects.filter(kind__in=kinds).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_upgrades, remove_upgrades),
    ]
