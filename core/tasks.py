"""Периодические задачи рынка."""

from celery import shared_task
from channels.layers import get_channel_layer
from django.db import close_old_connections

from core import market
from core.models import Asset
from core.utils import async_send_to_group


def advance_all_assets() -> list[dict]:
    """Двинуть все активы на один тик и вернуть свежие котировки."""
    quotes = []
    for asset in Asset.objects.all().order_by('ticker'):
        state = market.market_state(asset)
        quotes.append({
            'id': state['id'],
            'ticker': state['ticker'],
            'name': state['name'],
            'price': state['price'],
            'change_pct': state['change_pct'],
        })

    if quotes:
        async_send_to_group('market', {'type': 'price.update', 'data': {'assets': quotes}})
    return quotes


@shared_task(ignore_result=True)
def advance_market_task():
    close_old_connections()
    advance_all_assets()
