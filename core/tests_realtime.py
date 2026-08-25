"""Тесты реалтайма: задача рынка и WebSocket-консьюмер."""

from datetime import timedelta
from unittest import IsolatedAsyncioTestCase, mock

from channels.layers import InMemoryChannelLayer, channel_layers
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.utils import timezone

from config.asgi import application
from core import market
from core.models import Asset
from core.tasks import advance_all_assets


class AdvanceAllAssetsTest(TestCase):
    def setUp(self):
        # Изолируемся от сидовых активов миграций
        Asset.objects.all().delete()

    def _backdate(self, asset, seconds):
        Asset.objects.filter(pk=asset.pk).update(
            last_tick_at=timezone.now() - timedelta(seconds=seconds),
        )
        asset.refresh_from_db()

    def test_advances_every_asset_and_returns_quotes(self):
        first = Asset.objects.create(
            ticker='AAA', name='А', mu=0.0, sigma=0.01,
            price=100.0, last_tick_at=timezone.now(),
        )
        second = Asset.objects.create(
            ticker='BBB', name='Б', mu=0.0, sigma=0.01,
            price=50.0, last_tick_at=timezone.now(),
        )
        self._backdate(first, market.TICK_INTERVAL * 3)
        self._backdate(second, market.TICK_INTERVAL * 3)

        quotes = advance_all_assets()

        self.assertEqual(len(quotes), 2)
        by_ticker = {q['ticker']: q for q in quotes}
        self.assertIn('AAA', by_ticker)
        self.assertIn('price', by_ticker['AAA'])
        self.assertGreater(by_ticker['AAA']['price'], 0)
        self.assertGreater(by_ticker['BBB']['price'], 0)


class MarketConsumerTest(IsolatedAsyncioTestCase):
    async def test_connect_and_receive_broadcast(self):
        # Герметичность: подкладываем выделенный слой напрямую в менеджер,
        # чтобы тест не зависел от состояния глобального кэша слоёв
        layer = InMemoryChannelLayer()
        with mock.patch.object(channel_layers, 'backends', {'default': layer}):
            communicator = WebsocketCommunicator(application, '/ws/market/')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            payload = {
                'assets': [{'id': 1, 'ticker': 'TST', 'name': 'Тест',
                            'price': 1.23, 'change_pct': 0.5}],
            }
            await layer.group_send(
                'market',
                {'type': 'price.update', 'data': payload},
            )

            response = await communicator.receive_json_from(timeout=2)
            self.assertEqual(response, payload)

            await communicator.disconnect()
