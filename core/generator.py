"""Процедурный генератор компаний для биржи.

Новые активы появляются сами («IPO»): случайный тикер, название
из конструктора и архетип риска — от голубых фишек до мемных монет.
"""

import random

from django.utils import timezone

from core.models import Asset

MAX_ASSETS = 12          # больше не плодим
IPO_CHANCE = 0.25        # шанс IPO при открытии страницы биржи

_PREFIXES = [
    'Пиксель', 'Крипто', 'Нео', 'Гипер', 'Мега', 'Квант', 'Био',
    'Агро', 'Робо', 'Лазер', 'Нано', 'Вирт', 'Смарт', 'Экстра',
]
_CORES = [
    'Трейд', 'Фарм', 'Тех', 'Шип', 'Кофе', 'Пицца', 'Спейс',
    'Гейм', 'Мем', 'Лампа', 'Дрон', 'Сок', 'Носок', 'Тостер',
]
_SUFFIXES = [
    'Холдинг', 'Групп', 'Индастриз', 'Корп', 'И Ко',
    'Интернешнл', 'Лабс', 'Юнион', 'Консорциум',
]

# архетип: (доля, сигма_мин, сигма_макс, цена_мин, цена_макс)
_ARCHETYPES = {
    'bluechip': (0.35, 0.002, 0.004, 150, 300),
    'growth': (0.30, 0.006, 0.009, 50, 120),
    'meme': (0.25, 0.012, 0.02, 5, 40),
    'junk': (0.10, 0.02, 0.03, 0.3, 3),
}
_MU_RANGE = (0.00001, 0.00008)

_TICKER_ALPHABET = 'BCDFGHKLMNPRSTVXZ'


def _pick_archetype() -> str:
    r = random.random()
    cumulative = 0.0
    for name, (share, *_rest) in _ARCHETYPES.items():
        cumulative += share
        if r <= cumulative:
            return name
    return 'meme'


def _random_ticker(existing: set[str]) -> str:
    for _ in range(50):
        letters = ''.join(random.choices(_TICKER_ALPHABET, k=3))
        ticker = letters + str(random.randint(1, 99))
        if ticker not in existing:
            return ticker
    raise RuntimeError('Не удалось сгенерировать уникальный тикер')


def generate_company() -> Asset:
    """Создать одну новую компанию."""
    existing_tickers = set(Asset.objects.values_list('ticker', flat=True))

    archetype = _pick_archetype()
    _, sigma_min, sigma_max, price_min, price_max = _ARCHETYPES[archetype]

    name = '{}{} {}'.format(
        random.choice(_PREFIXES),
        random.choice(_CORES).lower(),
        random.choice(_SUFFIXES),
    )

    return Asset.objects.create(
        ticker=_random_ticker(existing_tickers),
        name=name,
        mu=random.uniform(*_MU_RANGE),
        sigma=random.uniform(sigma_min, sigma_max),
        price=round(random.uniform(price_min, price_max), 2),
        last_tick_at=timezone.now(),
    )


def maybe_run_ipo() -> Asset | None:
    """Лениво и вероятностно вывести компанию на биржу.

    Вызывается при загрузке страницы рынка: пока компаний меньше лимита,
    каждый вызов может (с шансом IPO_CHANCE) создать новую.
    """
    if Asset.objects.count() >= MAX_ASSETS:
        return None
    if random.random() > IPO_CHANCE:
        return None
    return generate_company()
