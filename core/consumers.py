from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

MARKET_GROUP = 'market'


class MarketConsumer(JsonWebsocketConsumer):
    """Рассылает всем подключённым клиентам котировки рынка."""

    def connect(self):
        async_to_sync(self.channel_layer.group_add)(MARKET_GROUP, self.channel_name)
        self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(MARKET_GROUP, self.channel_name)

    def price_update(self, event):
        """Тик котировок (celery)."""
        self.send_json(event['data'])

    def market_event(self, event):
        """Рыночное событие: крах/хайп/памп/дамп."""
        self.send_json(event['data'])
