import math
import random

from django.utils import timezone

from core import achievements
from core.models import Profile, Upgrade, UserUpgrade

ENERGY_REGEN_PER_SECOND = 0.5
CRIT_MULTIPLIER = 5
BASE_CRIT_CHANCE = 0.05
MAX_CRIT_CHANCE = 0.60
OFFLINE_INCOME_CAP_SECONDS = 2 * 60 * 60


def _elapsed_seconds(profile: Profile) -> float:
    return max(0.0, (timezone.now() - profile.last_seen).total_seconds())


def sync_profile(profile: Profile) -> None:
    """Лениво начисляет реген энергии и оффлайн-доход с прошлого визита."""
    elapsed = _elapsed_seconds(profile)

    regenerated = profile.energy + elapsed * ENERGY_REGEN_PER_SECOND
    profile.energy = min(int(regenerated), profile.max_energy)

    auto_level = get_level(profile, Upgrade.Kind.AUTO_CLICKER)
    if auto_level > 0:
        rate = auto_rate_per_second(auto_level)
        income_seconds = min(elapsed, OFFLINE_INCOME_CAP_SECONDS)
        profile.coins += int(math.floor(rate * income_seconds))

    profile.last_seen = timezone.now()
    profile.save(update_fields=['energy', 'coins', 'last_seen'])


def get_level(profile: Profile, kind: str) -> int:
    user_upgrade = profile.upgrades.select_related('upgrade').filter(
        upgrade__kind=kind,
    ).first()
    return user_upgrade.level if user_upgrade else 0


def click_power(profile: Profile) -> int:
    return 1 + get_level(profile, Upgrade.Kind.CLICK_POWER)


def crit_chance(profile: Profile) -> float:
    level = get_level(profile, Upgrade.Kind.CRIT_CHANCE)
    raw = BASE_CRIT_CHANCE + level * 0.02
    return min(raw, MAX_CRIT_CHANCE)


def auto_rate_per_second(level: int) -> float:
    return level * 0.5


def stats(profile: Profile) -> dict:
    return {
        'click_power': click_power(profile),
        'crit_chance': round(crit_chance(profile), 4),
        'auto_rate': round(auto_rate_per_second(get_level(profile, Upgrade.Kind.AUTO_CLICKER)), 2),
        'max_energy': profile.max_energy,
    }


def do_click(profile: Profile) -> dict:
    """Один клик: трата энергии и начисление монет (с шансом крита)."""
    sync_profile(profile)

    if profile.effective_energy() < 1:
        return {'ok': False, 'error': 'no_energy'}

    profile.energy -= 1
    profile.total_clicks += 1

    gained = click_power(profile)
    crit = random.random() < crit_chance(profile)
    if crit:
        gained *= CRIT_MULTIPLIER

    profile.coins += gained
    profile.save(update_fields=['energy', 'total_clicks', 'coins'])

    return {
        'ok': True,
        'gained': gained,
        'crit': crit,
        'coins': profile.coins,
        'energy': profile.effective_energy(),
        'total_clicks': profile.total_clicks,
        'achievements': achievements.check_after_click(profile),
    }


def upgrade_cost(profile: Profile, upgrade: Upgrade) -> int | None:
    """Текущая цена апгрейда для профиля или None, если достигнут лимит уровня."""
    level = get_level(profile, upgrade.kind)
    if level >= 10:
        return None
    return upgrade.cost_for_level(level)


def buy_upgrade(profile: Profile, upgrade: Upgrade) -> dict:
    """Покупка апгрейда: списание монет и повышение уровня."""
    sync_profile(profile)

    cost = upgrade_cost(profile, upgrade)
    if cost is None:
        return {'ok': False, 'error': 'max_level'}
    if profile.coins < cost:
        return {'ok': False, 'error': 'not_enough_coins'}

    profile.coins -= cost
    if upgrade.kind == Upgrade.Kind.MAX_ENERGY:
        profile.max_energy_level += 1

    user_upgrade, _ = UserUpgrade.objects.get_or_create(
        profile=profile,
        upgrade=upgrade,
        defaults={'level': 0},
    )
    user_upgrade.level += 1
    user_upgrade.save()

    profile.save(update_fields=['coins', 'max_energy_level'])

    return {
        'ok': True,
        'spent': cost,
        'level': user_upgrade.level,
        'coins': profile.coins,
        **stats(profile),
    }
