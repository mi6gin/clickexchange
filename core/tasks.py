"""Периодические задачи рынка."""

from celery import shared_task
from django.db import close_old_connections

from core import events, market


@shared_task(ignore_result=True)
def advance_market_task():
    close_old_connections()
    quotes = market.all_quotes()

    if quotes:
        from core.utils import async_send_to_group

        async_send_to_group('market', {'type': 'price.update', 'data': {'assets': quotes}})

    events.maybe_trigger_event()
