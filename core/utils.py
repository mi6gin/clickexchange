"""Мостик между синхронным кодом (celery, views) и async channel layer."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def async_send_to_group(group: str, message: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, message)
