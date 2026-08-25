"""Торговая логика: покупка, продажа, портфель."""

import math

from django.db import transaction

from core import achievements
from core.market import advance_market
from core.models import Asset, Holding, Profile, Transaction


@transaction.atomic
def buy(profile: Profile, asset: Asset, quantity: int) -> dict:
    """Купить quantity штук по текущей цене (с догоном рынка)."""
    if quantity <= 0:
        return {'ok': False, 'error': 'invalid_quantity'}

    asset = advance_market(asset)
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    profile = Profile.objects.select_for_update().get(pk=profile.pk)

    price = asset.price
    cost = math.ceil(quantity * price)
    if profile.coins < cost:
        return {'ok': False, 'error': 'not_enough_coins'}

    profile.coins -= cost

    holding, _ = Holding.objects.select_for_update().get_or_create(
        profile=profile,
        asset=asset,
        defaults={'avg_price': 0.0},
    )
    total_qty = holding.quantity + quantity
    holding.avg_price = (
        holding.avg_price * holding.quantity + quantity * price
    ) / total_qty
    holding.quantity = total_qty
    holding.save()

    profile.save(update_fields=['coins'])
    Transaction.objects.create(
        profile=profile,
        asset=asset,
        side=Transaction.Side.BUY,
        quantity=quantity,
        price=price,
        total=cost,
    )

    return {
        'ok': True,
        'side': 'buy',
        'quantity': quantity,
        'price': round(price, 4),
        'spent': cost,
        'coins': profile.coins,
        'achievements': achievements.check_after_trade(profile),
    }


@transaction.atomic
def sell(profile: Profile, asset: Asset, quantity: int) -> dict:
    """Продать quantity штук по текущей цене."""
    if quantity <= 0:
        return {'ok': False, 'error': 'invalid_quantity'}

    asset = advance_market(asset)
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    profile = Profile.objects.select_for_update().get(pk=profile.pk)

    try:
        holding = Holding.objects.select_for_update().get(
            profile=profile,
            asset=asset,
        )
    except Holding.DoesNotExist:
        return {'ok': False, 'error': 'no_position'}
    if holding.quantity < quantity:
        return {'ok': False, 'error': 'not_enough_assets'}

    price = asset.price
    proceeds = math.floor(quantity * price)
    realized_pnl = (price - holding.avg_price) * quantity

    profile.coins += proceeds
    holding.quantity -= quantity
    if holding.quantity == 0:
        holding.delete()
    else:
        holding.save(update_fields=['quantity'])

    profile.save(update_fields=['coins'])
    Transaction.objects.create(
        profile=profile,
        asset=asset,
        side=Transaction.Side.SELL,
        quantity=quantity,
        price=price,
        total=proceeds,
    )

    return {
        'ok': True,
        'side': 'sell',
        'quantity': quantity,
        'price': round(price, 4),
        'earned': proceeds,
        'realized_pnl': round(realized_pnl, 2),
        'coins': profile.coins,
        'achievements': achievements.check_after_trade(profile, realized_pnl),
    }


def portfolio_summary(profile: Profile) -> dict:
    """Портфель с актуальными ценами и общий капитал."""
    rows = []
    invested_value = 0.0
    unrealized_pnl = 0.0

    for holding in profile.portfolio.select_related('asset'):
        current_value = holding.quantity * holding.asset.price
        invested_value += current_value
        pnl = holding.unrealized_pnl
        unrealized_pnl += pnl
        rows.append({
            'id': holding.id,
            'ticker': holding.asset.ticker,
            'quantity': holding.quantity,
            'avg_price': round(holding.avg_price, 4),
            'current_price': round(holding.asset.price, 4),
            'value': round(current_value, 2),
            'unrealized_pnl': round(pnl, 2),
        })

    return {
        'holdings': rows,
        'invested_value': round(invested_value, 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
    }
