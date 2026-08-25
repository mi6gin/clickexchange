"""Рыночные события: крахи, хайпы, пампы и дампы.

С небольшим шансом срабатывают при очередном тике рынка (Celery).
Событие шокирует цену актива (или всего рынка), пишется в историю
и рассылается клиентам по WebSocket.
"""

import random

from core.utils import async_send_to_group
from core.models import Asset, MarketEvent

EVENT_CHANCE = 0.02  # шанс за тик (~раз в 4 минуты)

# kind → (весь ли рынок, диапазон множителя, шаблоны сообщений)
EVENT_SPECS = {
    MarketEvent.Kind.CRASH: (
        True,
        (0.5, 0.65),
        ['💥 КРАХ! Рынок обвалился, все в панике', '☠️ Чёрный вторник: всё горит'],
    ),
    MarketEvent.Kind.HYPE: (
        False,
        (2.0, 3.5),
        ['🚀 {ticker} улетает в космос на хайпе!', '🔥 Твитнул Илон — {ticker} взлетела'],
    ),
    MarketEvent.Kind.PUMP: (
        False,
        (1.4, 1.9),
        ['📈 Памп! {ticker} растёт на новостях', '🤑 Киты закупают {ticker}'],
    ),
    MarketEvent.Kind.DUMP: (
        False,
        (0.45, 0.7),
        ['📉 Дамп! {ticker} сливается', '😱 Скандальный отчёт обрушил {ticker}'],
    ),
}


def _pick_kind() -> str:
    # Крах редкий, остальное равновероятно
    return random.choices(
        list(EVENT_SPECS.keys()),
        weights=[4, 30, 33, 33],
        k=1,
    )[0]


def apply_event(kind: str, asset: Asset | None = None) -> MarketEvent | None:
    """Применить шок события к цене и записать его в историю."""
    market_wide, (mult_min, mult_max), templates = EVENT_SPECS[kind]

    assets = list(Asset.objects.all()) if market_wide else [asset or random.choice(Asset.objects.all())]
    if not assets:
        return None

    multiplier = round(random.uniform(mult_min, mult_max), 3)
    for a in assets:
        a.price = max(round(a.price * multiplier, 4), 0.01)
        a.save(update_fields=['price'])

    template = random.choice(templates)
    message = template.format(ticker=assets[0].ticker)

    event = MarketEvent.objects.create(
        kind=kind,
        asset=None if market_wide else assets[0],
        message=message,
        multiplier=multiplier,
    )

    from core import market  # локальный импорт против цикла

    async_send_to_group('market', {
        'type': 'market.event',
        'data': {
            'event': {
                'kind': event.kind,
                'message': event.message,
                'multiplier': event.multiplier,
                'is_good': event.is_good,
            },
            'assets': market.all_quotes(),
        },
    })
    return event


def maybe_trigger_event() -> MarketEvent | None:
    """Ленивый триггер с шансом EVENT_CHANCE за вызов."""
    if not Asset.objects.exists():
        return None
    if random.random() > EVENT_CHANCE:
        return None
    return apply_event(_pick_kind())
