from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь',
    )
    coins = models.PositiveBigIntegerField(default=0, verbose_name='Монеты')
    total_clicks = models.PositiveBigIntegerField(default=0, verbose_name='Всего кликов')
    energy = models.PositiveIntegerField(default=100, verbose_name='Энергия')
    max_energy_level = models.PositiveIntegerField(default=0, verbose_name='Уровень апгрейда энергии')
    last_seen = models.DateTimeField(auto_now_add=True, verbose_name='Последний визит')

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'

    def __str__(self):
        return f'Профиль {self.user.username}'

    @property
    def max_energy(self) -> int:
        return 100 + self.max_energy_level * 25

    def effective_energy(self) -> int:
        return min(self.energy, self.max_energy)


class Upgrade(models.Model):
    class Kind(models.TextChoices):
        CLICK_POWER = 'click_power', 'Сила клика'
        AUTO_CLICKER = 'auto_clicker', 'Автокликер'
        CRIT_CHANCE = 'crit_chance', 'Шанс крита'
        MAX_ENERGY = 'max_energy', 'Максимум энергии'

    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        unique=True,
        verbose_name='Тип апгрейда',
    )
    base_cost = models.PositiveBigIntegerField(verbose_name='Базовая цена')
    cost_multiplier = models.FloatField(default=1.5, verbose_name='Множитель цены')
    effect_per_level = models.FloatField(verbose_name='Эффект за уровень')

    class Meta:
        verbose_name = 'Апгрейд'
        verbose_name_plural = 'Апгрейды'

    def __str__(self):
        return self.get_kind_display()

    def cost_for_level(self, level: int) -> int:
        return int(self.base_cost * (self.cost_multiplier ** level))


class UserUpgrade(models.Model):
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='upgrades',
        verbose_name='Профиль',
    )
    upgrade = models.ForeignKey(
        Upgrade,
        on_delete=models.CASCADE,
        related_name='owners',
        verbose_name='Апгрейд',
    )
    level = models.PositiveIntegerField(default=0, verbose_name='Уровень')

    class Meta:
        verbose_name = 'Апгрейд игрока'
        verbose_name_plural = 'Апгрейды игроков'
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'upgrade'],
                name='unique_profile_upgrade',
            ),
        ]

    def __str__(self):
        return f'{self.profile} — {self.upgrade} ур. {self.level}'


class Asset(models.Model):
    """Виртуальный актив на игровой бирже."""

    ticker = models.CharField(max_length=10, unique=True, verbose_name='Тикер')
    name = models.CharField(max_length=64, verbose_name='Название')
    mu = models.FloatField(verbose_name='Дрейф (за секунду)')
    sigma = models.FloatField(verbose_name='Волатильность (за √секунды)')
    price = models.FloatField(default=100.0, verbose_name='Текущая цена')
    last_tick_at = models.DateTimeField(verbose_name='Время последнего тика')

    class Meta:
        verbose_name = 'Актив'
        verbose_name_plural = 'Активы'

    def __str__(self):
        return f'{self.ticker} — {self.name}'


class PriceTick(models.Model):
    """Одна точка цены актива (история для свечей)."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='ticks',
        verbose_name='Актив',
    )
    price = models.FloatField(verbose_name='Цена')
    ts = models.DateTimeField(db_index=True, verbose_name='Время тика')

    class Meta:
        verbose_name = 'Тик цены'
        verbose_name_plural = 'Тики цен'
        ordering = ['ts']

    def __str__(self):
        return f'{self.asset.ticker} {self.price} @ {self.ts:%H:%M:%S}'


class Holding(models.Model):
    """Позиция игрока в активе."""

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='portfolio',
        verbose_name='Профиль',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='holders',
        verbose_name='Актив',
    )
    quantity = models.PositiveBigIntegerField(default=0, verbose_name='Количество')
    avg_price = models.FloatField(default=0.0, verbose_name='Средняя цена покупки')

    class Meta:
        verbose_name = 'Позиция'
        verbose_name_plural = 'Портфель'
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'asset'],
                name='unique_profile_asset',
            ),
        ]

    def __str__(self):
        return f'{self.profile}: {self.quantity} × {self.asset.ticker}'

    @property
    def unrealized_pnl(self) -> float:
        return (self.asset.price - self.avg_price) * self.quantity


class Transaction(models.Model):
    class Side(models.TextChoices):
        BUY = 'buy', 'Покупка'
        SELL = 'sell', 'Продажа'

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='trades',
        verbose_name='Профиль',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='trades',
        verbose_name='Актив',
    )
    side = models.CharField(max_length=4, choices=Side.choices, verbose_name='Сторона')
    quantity = models.PositiveBigIntegerField(verbose_name='Количество')
    price = models.FloatField(verbose_name='Цена сделки')
    total = models.FloatField(verbose_name='Сумма')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время')

    class Meta:
        verbose_name = 'Сделка'
        verbose_name_plural = 'Сделки'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_side_display()} {self.quantity} {self.asset.ticker} по {self.price}'


class MarketEvent(models.Model):
    class Kind(models.TextChoices):
        CRASH = 'crash', 'Крах'
        HYPE = 'hype', 'Хайп'
        PUMP = 'pump', 'Памп'
        DUMP = 'dump', 'Дамп'

    kind = models.CharField(max_length=10, choices=Kind.choices, verbose_name='Тип')
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name='Затронутый актив (None — весь рынок)',
    )
    message = models.CharField(max_length=200, verbose_name='Сообщение')
    multiplier = models.FloatField(verbose_name='Множитель цены')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Время')

    class Meta:
        verbose_name = 'Рыночное событие'
        verbose_name_plural = 'Рыночные события'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.kind}] {self.message}'

    @property
    def is_good(self) -> bool:
        return self.multiplier >= 1


class Achievement(models.Model):
    code = models.CharField(max_length=32, unique=True, verbose_name='Код')
    name = models.CharField(max_length=64, verbose_name='Название')
    description = models.CharField(max_length=200, verbose_name='Описание')
    icon = models.CharField(max_length=8, default='🏆', verbose_name='Иконка')

    class Meta:
        verbose_name = 'Достижение'
        verbose_name_plural = 'Достижения'

    def __str__(self):
        return f'{self.icon} {self.name}'


class UserAchievement(models.Model):
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='achievements',
        verbose_name='Профиль',
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='holders',
        verbose_name='Достижение',
    )
    awarded_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда получено')

    class Meta:
        verbose_name = 'Достижение игрока'
        verbose_name_plural = 'Достижения игроков'
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'achievement'],
                name='unique_profile_achievement',
            ),
        ]

    def __str__(self):
        return f'{self.profile}: {self.achievement}'
