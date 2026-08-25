"""Ценовой движок: геометрическое броуновское движение с ленивыми тиками.

Реального времени пока нет (это этап 3): цена «догоняет» текущий момент
при каждом обращении — при загрузке страницы или запросе API.
"""

import math
import random

from django.db import transaction
from django.utils import timezone

from core.models import Asset, PriceTick

TICK_INTERVAL = 5         # секунд между тиками
MAX_PENDING_TICKS = 300   # максимум догоняющих тиков за один вызов
TICKS_PER_CANDLE = 8      # тиков в одной свече
MAX_TICKS_KEPT = 2000     # хранить не больше этого числа тиков на актив


def gbm_step(price: float, mu: float, sigma: float, dt: float) -> float:
    """Один шаг GBM: S' = S·exp((μ−σ²/2)dt + σ√dt·Z)."""
    z = random.gauss(0.0, 1.0)
    return price * math.exp((mu - sigma * sigma / 2) * dt + sigma * math.sqrt(dt) * z)


@transaction.atomic
def advance_market(asset: Asset) -> Asset:
    """Двигает цену актива до текущего момента.

    Долгий простой не «сжимает» историю: симулируем не больше
    MAX_PENDING_TICKS шагов, остальное время пропускаем.
    """
    now = timezone.now()
    asset = Asset.objects.select_for_update().get(pk=asset.pk)

    elapsed = max(0.0, (now - asset.last_tick_at).total_seconds())
    n_ticks = int(elapsed // TICK_INTERVAL)
    if n_ticks <= 0:
        return asset

    simulated = min(n_ticks, MAX_PENDING_TICKS)
    dt = TICK_INTERVAL
    ts = asset.last_tick_at
    price = asset.price

    new_ticks = []
    for _ in range(simulated):
        price = max(gbm_step(price, asset.mu, asset.sigma, dt), 0.01)
        ts += timezone.timedelta(seconds=dt)
        new_ticks.append(PriceTick(asset=asset, price=price, ts=ts))

    PriceTick.objects.bulk_create(new_ticks)

    # Не даём истории расти бесконечно
    total = PriceTick.objects.filter(asset=asset).count()
    if total > MAX_TICKS_KEPT:
        cutoff = (
            PriceTick.objects.filter(asset=asset)
            .values_list('ts', flat=True)
            .order_by('-ts')[MAX_TICKS_KEPT - 1]
        )
        PriceTick.objects.filter(asset=asset, ts__lt=cutoff).delete()

    asset.price = price
    asset.last_tick_at = now if n_ticks > MAX_PENDING_TICKS else ts
    asset.save(update_fields=['price', 'last_tick_at'])
    return asset


def get_candles(asset: Asset, count: int = 60) -> list[dict]:
    """Последние `count` свечей OHLC из истории тиков."""
    ticks = list(
        asset.ticks.values_list('ts', 'price').order_by('-ts')[
            : count * TICKS_PER_CANDLE + 1
        ],
    )
    ticks.reverse()

    candles = []
    for i in range(TICKS_PER_CANDLE, len(ticks) + 1, TICKS_PER_CANDLE):
        start = i - TICKS_PER_CANDLE
        window = [p for _, p in ticks[start:i]]
        if start > 0:
            prev_close = ticks[start - 1][1]
        else:
            prev_close = window[0]
        candles.append({
            'o': prev_close,
            'h': max(window),
            'l': min(window),
            'c': window[-1],
            't': ticks[i - 1][0].isoformat(),
        })
    return candles


def market_state(asset: Asset) -> dict:
    """Состояние актива для API: цена и свечи (заодно двигает рынок)."""
    asset = advance_market(asset)
    candles = get_candles(asset)
    first_price = candles[0]['o'] if candles else asset.price
    return {
        'id': asset.id,
        'ticker': asset.ticker,
        'name': asset.name,
        'price': round(asset.price, 4),
        'change_pct': round((asset.price / first_price - 1) * 100, 2),
        'candles': candles,
    }
