"""Выдача достижений. Все проверки идемпотентны (get_or_create)."""

from core.models import Achievement, Profile, Transaction, UserAchievement

MILLION = 1_000_000
CLICK_THRESHOLDS = {100: 'clicker_100', 1000: 'clicker_1000'}
TRADE_COUNT_THRESHOLD = 10
DIAMOND_DRAWDOWN = -0.5  # просадка позиции на 50%+


def award(profile: Profile, code: str) -> str | None:
    """Выдать достижение; вернуть название, если оно новое."""
    try:
        achievement = Achievement.objects.get(code=code)
    except Achievement.DoesNotExist:
        return None

    _, created = UserAchievement.objects.get_or_create(
        profile=profile,
        achievement=achievement,
    )
    return f'{achievement.icon} {achievement.name}' if created else None


def net_worth(profile: Profile) -> float:
    """Чистый капитал: монеты + стоимость всех позиций по текущим ценам."""
    value = 0.0
    for holding in profile.portfolio.select_related('asset'):
        value += holding.quantity * holding.asset.price
    return profile.coins + value


def check_after_click(profile: Profile) -> list[str]:
    """Ачивки за клики и богатство."""
    awarded = []
    for threshold, code in CLICK_THRESHOLDS.items():
        if profile.total_clicks >= threshold:
            name = award(profile, code)
            if name:
                awarded.append(name)

    name = _check_wealth(profile)
    if name:
        awarded.append(name)
    return awarded


def check_after_trade(profile: Profile, realized_pnl: float | None = None) -> list[str]:
    """Ачивки за сделки: количество, бумажные/алмазные руки, богатство."""
    awarded = []

    name = award(profile, 'first_trade')
    if name:
        awarded.append(name)

    trades_count = Transaction.objects.filter(profile=profile).count()
    if trades_count >= TRADE_COUNT_THRESHOLD:
        name = award(profile, 'ten_trades')
        if name:
            awarded.append(name)

    if realized_pnl is not None and realized_pnl < 0:
        name = award(profile, 'paper_hands')
        if name:
            awarded.append(name)

    for holding in profile.portfolio.select_related('asset'):
        invested = holding.avg_price * holding.quantity
        if invested > 0 and holding.unrealized_pnl / invested <= DIAMOND_DRAWDOWN:
            name = award(profile, 'diamond_hands')
            if name:
                awarded.append(name)
            break

    name = _check_wealth(profile)
    if name:
        awarded.append(name)
    return awarded


def _check_wealth(profile: Profile) -> str | None:
    if net_worth(profile) >= MILLION:
        return award(profile, 'millionaire')
    return None
