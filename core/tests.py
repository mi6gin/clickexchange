import json
import math
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import broker, market, services
from core.models import Asset, Holding, PriceTick, Profile, Transaction, Upgrade


def make_user(username='tester'):
    return User.objects.create_user(username=username, password='pass12345')


class ProfileSignalTest(TestCase):
    def test_profile_created_with_user(self):
        user = make_user()
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_defaults(self):
        profile = make_user().profile
        self.assertEqual(profile.coins, 0)
        self.assertEqual(profile.energy, 100)


class ClickTest(TestCase):
    def setUp(self):
        self.profile = make_user().profile

    def test_click_spends_energy_and_gives_coins(self):
        # Изолируем рандом: без крита (иначе тест флакает)
        with mock.patch.object(services.random, 'random', return_value=0.5):
            result = services.do_click(self.profile)

        self.assertTrue(result['ok'])
        self.assertFalse(result['crit'])
        self.assertEqual(result['gained'], 1)
        self.assertEqual(self.profile.coins, 1)
        self.assertEqual(self.profile.energy, 99)
        self.assertEqual(self.profile.total_clicks, 1)

    def test_crit_multiplies_gain(self):
        with mock.patch.object(services.random, 'random', return_value=0.0):
            result = services.do_click(self.profile)

        self.assertTrue(result['crit'])
        self.assertEqual(result['gained'], services.CRIT_MULTIPLIER)
        self.assertEqual(self.profile.coins, services.CRIT_MULTIPLIER)

    def test_click_without_energy_fails(self):
        self.profile.energy = 0
        self.profile.save()

        result = services.do_click(self.profile)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'no_energy')
        self.assertEqual(self.profile.total_clicks, 0)

    def test_energy_never_exceeds_max_after_upgrade(self):
        self.profile.max_energy_level = 2
        self.profile.energy = 500
        self.profile.save()

        self.assertEqual(self.profile.effective_energy(), self.profile.max_energy)


class SyncProfileTest(TestCase):
    def setUp(self):
        self.profile = make_user().profile

    def _backdate(self, seconds):
        Profile.objects.filter(pk=self.profile.pk).update(
            last_seen=timezone.now() - timedelta(seconds=seconds),
        )
        self.profile.refresh_from_db()

    def test_energy_regen(self):
        self.profile.energy = 50
        self.profile.save()
        self._backdate(60)

        services.sync_profile(self.profile)

        self.profile.refresh_from_db()
        expected = min(int(50 + 60 * services.ENERGY_REGEN_PER_SECOND), self.profile.max_energy)
        self.assertEqual(self.profile.energy, expected)

    def test_regen_capped_at_max(self):
        self.profile.energy = 100
        self.profile.save()
        self._backdate(3600)

        services.sync_profile(self.profile)
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.energy, self.profile.max_energy)

    def test_offline_income(self):
        upgrade = Upgrade.objects.get(kind=Upgrade.Kind.AUTO_CLICKER)
        self.profile.upgrades.create(upgrade=upgrade, level=2)
        self._backdate(600)  # 10 минут

        services.sync_profile(self.profile)
        self.profile.refresh_from_db()

        rate = services.auto_rate_per_second(2)
        self.assertEqual(self.profile.coins, int(rate * 600))

    def test_offline_income_capped_at_two_hours(self):
        upgrade = Upgrade.objects.get(kind=Upgrade.Kind.AUTO_CLICKER)
        self.profile.upgrades.create(upgrade=upgrade, level=4)
        self._backdate(48 * 3600)

        services.sync_profile(self.profile)
        self.profile.refresh_from_db()

        rate = services.auto_rate_per_second(4)
        self.assertEqual(
            self.profile.coins,
            int(rate * services.OFFLINE_INCOME_CAP_SECONDS),
        )


class BuyUpgradeTest(TestCase):
    def setUp(self):
        self.profile = make_user().profile
        self.click_power = Upgrade.objects.get(kind=Upgrade.Kind.CLICK_POWER)
        self.max_energy = Upgrade.objects.get(kind=Upgrade.Kind.MAX_ENERGY)

    def test_successful_purchase(self):
        self.profile.coins = self.click_power.base_cost
        self.profile.save()

        result = services.buy_upgrade(self.profile, self.click_power)

        self.assertTrue(result['ok'])
        self.assertEqual(result['level'], 1)
        self.assertEqual(self.profile.coins, 0)
        self.assertEqual(services.click_power(self.profile), 2)

    def test_cost_grows_with_level(self):
        self.profile.coins = 10_000_000
        self.profile.save()
        for level in range(5):
            cost = services.upgrade_cost(self.profile, self.click_power)
            services.buy_upgrade(self.profile, self.click_power)
            next_cost = services.upgrade_cost(self.profile, self.click_power)
            self.assertGreater(next_cost, cost)

    def test_not_enough_coins(self):
        result = services.buy_upgrade(self.profile, self.click_power)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'not_enough_coins')
        self.assertEqual(services.get_level(self.profile, self.click_power.kind), 0)

    def test_max_level_limit(self):
        self.profile.coins = 10_000_000_000
        self.profile.save()
        for _ in range(10):
            services.buy_upgrade(self.profile, self.max_energy)

        result = services.buy_upgrade(self.profile, self.max_energy)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'max_level')
        self.assertEqual(self.profile.max_energy_level, 10)


class ViewTest(TestCase):
    def test_home_redirects_anonymous_to_game_login(self):
        response = self.client.get(reverse('game'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_register_creates_profile_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newbie',
            'password1': 's3curePass!x',
            'password2': 's3curePass!x',
        })
        self.assertRedirects(response, reverse('game'))
        self.assertTrue(Profile.objects.filter(user__username='newbie').exists())

    def test_game_page_shows_upgrades(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse('game'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Апгрейды')

    def test_api_requires_login(self):
        response = self.client.post(reverse('api-click'))
        self.assertEqual(response.status_code, 302)

    def test_api_click(self):
        self.client.force_login(make_user())
        response = self.client.post(reverse('api-click'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['coins'], 1)
        self.assertEqual(data['energy'], 99)

    def test_api_buy_success_and_failure(self):
        profile = make_user().profile
        self.client.force_login(profile.user)
        upgrade = Upgrade.objects.get(kind=Upgrade.Kind.CLICK_POWER)

        poor = self.client.post(reverse('api-buy', args=[upgrade.id]))
        self.assertEqual(poor.status_code, 400)
        self.assertEqual(poor.json()['error'], 'not_enough_coins')

        profile.coins = upgrade.base_cost
        profile.save(update_fields=['coins'])
        rich = self.client.post(reverse('api-buy', args=[upgrade.id]))
        self.assertEqual(rich.status_code, 200)
        self.assertTrue(rich.json()['ok'])

    def test_api_state(self):
        profile = make_user().profile
        self.client.force_login(profile.user)
        response = self.client.get(reverse('api-state'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['coins'], 0)
        self.assertEqual(data['max_energy'], 100)


class SecurityTest(TestCase):
    def _post_login(self, username, password):
        return self.client.post(
            reverse('login'),
            {'username': username, 'password': password},
        )

    def test_new_passwords_use_argon2(self):
        user = make_user('argon2user')
        self.assertTrue(user.password.startswith('argon2'))

    def test_legacy_pbkdf2_hash_upgrades_on_login(self):
        user = make_user('legacy')
        User.objects.filter(pk=user.pk).update(
            password=make_password('pass12345', hasher='pbkdf2_sha256'),
        )
        user.refresh_from_db()
        self.assertTrue(user.password.startswith('pbkdf2'))

        response = self._post_login('legacy', 'pass12345')

        self.assertRedirects(response, reverse('game'))
        user.refresh_from_db()
        self.assertTrue(user.password.startswith('argon2'))

    def test_brute_force_lockout_after_limit(self):
        make_user('victim')

        # Первые (лимит - 1) неверных попыток проходят до формы логина
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            response = self._post_login('victim', 'wrong-pass')
            self.assertEqual(response.status_code, 200)

        # На лимитной попытке срабатывает блокировка (middleware отдаёт 429)
        self.assertEqual(
            self._post_login('victim', 'wrong-pass').status_code,
            429,
        )
        # Даже с верным паролем запрос блокируется
        self.assertEqual(
            self._post_login('victim', 'pass12345').status_code,
            429,
        )

    def test_lockout_resets_after_success(self):
        make_user('resetter')

        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self._post_login('resetter', 'wrong-pass')

        response = self._post_login('resetter', 'pass12345')
        self.assertRedirects(response, reverse('game'))


# ---------- Биржа (этап 2) ----------

from core import broker, market
from core.models import Asset, Holding, PriceTick, Transaction


def make_asset(**overrides):
    defaults = {
        'ticker': 'TEST',
        'name': 'Тестовая акция',
        'mu': 0.0,
        'sigma': 0.01,
        'price': 100.0,
        # По умолчанию рынок «стоит» — чтобы сделки шли по известной цене
        'last_tick_at': timezone.now(),
    }
    defaults.update(overrides)
    return Asset.objects.create(**defaults)


class MarketEngineTest(TestCase):
    def _backdate(self, asset, seconds):
        Asset.objects.filter(pk=asset.pk).update(
            last_tick_at=timezone.now() - timedelta(seconds=seconds),
        )
        asset.refresh_from_db()

    def test_advance_creates_ticks(self):
        asset = make_asset()
        self._backdate(asset, market.TICK_INTERVAL * 5)

        market.advance_market(asset)

        self.assertEqual(PriceTick.objects.filter(asset=asset).count(), 5)
        asset.refresh_from_db()
        self.assertGreater(asset.price, 0)
        # last_tick_at обновился до ~текущего момента
        self.assertLess(
            (timezone.now() - asset.last_tick_at).total_seconds(),
            market.TICK_INTERVAL,
        )

    def test_advance_capped_after_downtime(self):
        asset = make_asset()
        self._backdate(asset, market.TICK_INTERVAL * 100_000)  # очень долго офлайн

        market.advance_market(asset)

        self.assertEqual(
            PriceTick.objects.filter(asset=asset).count(),
            market.MAX_PENDING_TICKS,
        )

    def test_advance_is_noop_within_interval(self):
        asset = make_asset()
        self._backdate(asset, 2)

        market.advance_market(asset)

        self.assertEqual(PriceTick.objects.count(), 0)

    def test_gbm_step_positive_with_extreme_moves(self):
        price = make_asset().price
        with mock.patch.object(market.random, 'gauss', return_value=-10.0):
            new_price = market.gbm_step(price, mu=0.0, sigma=0.01, dt=10.0)
        self.assertGreater(new_price, 0)

    def test_get_candles_structure(self):
        asset = make_asset()
        total_ticks = market.TICKS_PER_CANDLE * 3  # ровно 3 свечи
        ticks = []
        ts = timezone.now() - timedelta(seconds=market.TICK_INTERVAL * total_ticks)
        for i in range(total_ticks):
            ticks.append(PriceTick(
                asset=asset,
                price=100 + i,
                ts=ts + timedelta(seconds=market.TICK_INTERVAL * i),
            ))
        PriceTick.objects.bulk_create(ticks)

        candles = market.get_candles(asset, count=60)

        self.assertEqual(len(candles), 3)
        first = candles[0]
        last = candles[-1]
        self.assertEqual(first['o'], 100)
        self.assertEqual(first['c'], 100 + market.TICKS_PER_CANDLE - 1)
        self.assertEqual(first['l'], 100)
        self.assertEqual(first['h'], 100 + market.TICKS_PER_CANDLE - 1)
        # Последняя свеча закрывается последним тиком
        self.assertEqual(last['c'], 100 + total_ticks - 1)


class BrokerTest(TestCase):
    def setUp(self):
        self.profile = make_user('trader').profile
        self.asset = make_asset()

    def test_buy_success(self):
        self.profile.coins = 1_000_000
        self.profile.save()

        result = broker.buy(self.profile, self.asset, 10)

        self.assertTrue(result['ok'])
        self.assertEqual(result['spent'], math.ceil(10 * 100))
        holding = Holding.objects.get(profile=self.profile, asset=self.asset)
        self.assertEqual(holding.quantity, 10)
        self.assertEqual(holding.avg_price, 100.0)
        self.assertTrue(Transaction.objects.filter(side='buy').exists())

    def test_buy_insufficient_coins(self):
        self.profile.coins = 50
        self.profile.save()

        result = broker.buy(self.profile, self.asset, 10)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'not_enough_coins')
        self.assertFalse(Holding.objects.exists())

    def test_buy_invalid_quantity(self):
        self.assertFalse(broker.buy(self.profile, self.asset, 0)['ok'])
        self.assertFalse(broker.buy(self.profile, self.asset, -3)['ok'])

    def test_avg_price_weighted(self):
        self.profile.coins = 10_000_000
        self.profile.save()

        broker.buy(self.profile, self.asset, 10)          # по 100
        Asset.objects.filter(pk=self.asset.pk).update(price=200.0)
        self.asset.refresh_from_db()
        broker.buy(self.profile, self.asset, 30)          # по 200

        holding = Holding.objects.get(profile=self.profile, asset=self.asset)
        expected = (10 * 100 + 30 * 200) / 40
        self.assertAlmostEqual(holding.avg_price, expected)

    def test_sell_success_with_profit(self):
        self.profile.coins = 1_000_000
        self.profile.save()
        broker.buy(self.profile, self.asset, 10)  # avg 100

        Asset.objects.filter(pk=self.asset.pk).update(price=150.0)
        self.asset.refresh_from_db()

        result = broker.sell(self.profile, self.asset, 10)

        self.assertTrue(result['ok'])
        self.assertEqual(result['earned'], int(10 * 150))
        self.assertEqual(result['realized_pnl'], 500.0)
        self.assertFalse(Holding.objects.exists())  # позиция закрыта полностью
        self.assertTrue(Transaction.objects.filter(side='sell').exists())

    def test_sell_more_than_owned(self):
        self.profile.coins = 1_000_000
        self.profile.save()
        broker.buy(self.profile, self.asset, 5)

        result = broker.sell(self.profile, self.asset, 10)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'not_enough_assets')

    def test_sell_without_position(self):
        result = broker.sell(self.profile, self.asset, 1)
        self.assertEqual(result['error'], 'no_position')

    def test_portfolio_summary(self):
        self.profile.coins = 1_000_000
        self.profile.save()
        broker.buy(self.profile, self.asset, 10)
        Asset.objects.filter(pk=self.asset.pk).update(price=120.0)
        self.asset.refresh_from_db()

        summary = broker.portfolio_summary(self.profile)

        self.assertEqual(summary['invested_value'], 1200.0)
        self.assertEqual(summary['unrealized_pnl'], 200.0)
        self.assertEqual(summary['holdings'][0]['ticker'], 'TEST')


class MarketViewTest(TestCase):
    def setUp(self):
        self.client.force_login(make_user('viewer').profile.user)
        self.asset = make_asset()

    def test_market_page_requires_login(self):
        response = Client(HTTP_HOST='localhost').get('/market/')
        self.assertEqual(response.status_code, 302)

    def test_market_page_renders(self):
        response = self.client.get(reverse('market'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TEST')

    def test_api_asset_advances_and_returns_state(self):
        response = self.client.get(f'/api/asset/{self.asset.id}/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('price', data)
        self.assertIn('candles', data)

    def test_api_trade_buy_and_sell(self):
        profile = Profile.objects.get(user__username='viewer')
        profile.coins = 1_000_000
        profile.save()

        buy_response = self.client.post(
            f'/api/trade/{self.asset.id}/buy/',
            data=json.dumps({'quantity': 5}),
            content_type='application/json',
        )
        self.assertEqual(buy_response.status_code, 200)
        self.assertTrue(buy_response.json()['ok'])
        self.assertIn('portfolio', buy_response.json())

        sell_response = self.client.post(
            f'/api/trade/{self.asset.id}/sell/',
            data=json.dumps({'quantity': 5}),
            content_type='application/json',
        )
        self.assertEqual(sell_response.status_code, 200)
        self.assertTrue(sell_response.json()['ok'])

    def test_api_trade_bad_side(self):
        response = self.client.post(f'/api/trade/{self.asset.id}/hodl/')
        self.assertEqual(response.status_code, 400)

    def test_game_links_to_market(self):
        response = self.client.get(reverse('game'))
        self.assertContains(response, '/market/')


# ---------- Генератор компаний (IPO) ----------

from core import generator


class GeneratorTest(TestCase):
    def setUp(self):
        # Изолируемся от сидовых активов миграций
        Asset.objects.all().delete()

    def test_generate_company_valid(self):
        asset = generator.generate_company()

        self.assertRegex(asset.ticker, r'^[A-Z]{3}\d{1,2}$')
        self.assertGreater(asset.price, 0)
        self.assertGreater(asset.sigma, 0)
        self.assertIn(' ', asset.name)

    def test_generated_tickers_unique(self):
        tickers = {generator.generate_company().ticker for _ in range(10)}
        self.assertEqual(len(tickers), 10)
        self.assertEqual(len(tickers), Asset.objects.count())

    def test_maybe_run_ipo_respects_cap(self):
        for _ in range(generator.MAX_ASSETS):
            generator.generate_company()

        with mock.patch.object(generator.random, 'random', return_value=0.0):
            self.assertIsNone(generator.maybe_run_ipo())
        self.assertEqual(Asset.objects.count(), generator.MAX_ASSETS)

    def test_maybe_run_ipo_probabilistic(self):
        with mock.patch.object(generator.random, 'random', return_value=0.9):
            self.assertIsNone(generator.maybe_run_ipo())
        with mock.patch.object(generator.random, 'random', return_value=0.0):
            self.assertIsNotNone(generator.maybe_run_ipo())

    def test_market_page_can_show_ipo_banner(self):
        self.client.force_login(make_user('ipoviewer').profile.user)
        with mock.patch.object(generator, 'maybe_run_ipo', return_value=None):
            response = self.client.get(reverse('market'))
        self.assertEqual(response.status_code, 200)

    def test_generate_assets_command(self):
        from django.core.management import call_command

        call_command('generate_assets', '3', stdout=open('/dev/null', 'w'))
        self.assertEqual(Asset.objects.count(), 3)
