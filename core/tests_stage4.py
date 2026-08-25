"""Тесты этапа 4: рыночные события, ачивки, лидерборд."""

import math
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import events
from core.broker import buy, sell
from core.models import Achievement, Asset, Holding, MarketEvent, Profile, UserAchievement
from core.services import do_click


def timezone_now():
    return timezone.now()


def make_user(username):
    return User.objects.create_user(username=username, password='pass12345')


def make_asset(**overrides):
    defaults = {
        'ticker': 'TEST',
        'name': 'Тестовая акция',
        'mu': 0.0,
        'sigma': 0.01,
        'price': 100.0,
        'last_tick_at': timezone_now(),
    }
    defaults.update(overrides)
    return Asset.objects.create(**defaults)


class MarketEventsTest(TestCase):
    def setUp(self):
        self.asset = make_asset()

    def test_apply_event_shocks_price_and_records(self):
        old_price = self.asset.price

        with mock.patch.object(events.random, 'uniform', return_value=0.5):
            event = events.apply_event(events.MarketEvent.Kind.PUMP, self.asset)

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.price, old_price * 0.5)
        self.assertFalse(event.is_good)
        self.assertIn('TEST', event.message)
        self.assertTrue(MarketEvent.objects.filter(kind='pump').exists())

    def test_market_wide_crash_hits_all_assets(self):
        second = make_asset(ticker='OTHR', price=200.0)

        with mock.patch.object(events.random, 'uniform', return_value=0.6):
            event = events.apply_event(events.MarketEvent.Kind.CRASH)

        self.asset.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(event.asset)  # событие на весь рынок
        self.assertEqual(self.asset.price, 60.0)
        self.assertEqual(second.price, 120.0)

    def test_maybe_trigger_respects_chance(self):
        with mock.patch.object(events.random, 'random', return_value=0.99):
            self.assertIsNone(events.maybe_trigger_event())
        with (
            mock.patch.object(events.random, 'random', return_value=0.0),
            mock.patch.object(events, '_pick_kind', return_value='dump'),
        ):
            event = events.maybe_trigger_event()
        self.assertIsNotNone(event)

    def test_market_page_shows_events_feed(self):
        client = Client(HTTP_HOST='localhost')
        client.force_login(make_user('ev'))

        with mock.patch.object(events.random, 'uniform', return_value=2.0):
            events.apply_event(events.MarketEvent.Kind.HYPE, self.asset)

        response = client.get(reverse('market'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'События рынка')


class AchievementsTest(TestCase):
    def setUp(self):
        self.user = make_user('ach')
        self.profile = self.user.profile
        self.asset = make_asset()

    def _earned_codes(self):
        return set(
            UserAchievement.objects.filter(profile=self.profile)
            .values_list('achievement__code', flat=True),
        )

    def test_click_achievements_awarded_once(self):
        self.profile.total_clicks = 100
        self.profile.save()

        awarded = do_click(self.profile)['achievements']
        self.assertIn('👆 Разминка', awarded)
        self.assertIn('clicker_100', self._earned_codes())

        # Повторно достижение не выдаётся
        Profile.objects.filter(pk=self.profile.pk).update(total_clicks=100)
        awarded_again = do_click(self.profile)['achievements']
        self.assertNotIn('👆 Разминка', awarded_again)

    def test_paper_hands_on_losing_sell(self):
        self.profile.coins = 1_000_000
        self.profile.save()
        buy(self.profile, self.asset, 10)  # по 100

        Asset.objects.filter(pk=self.asset.pk).update(price=40.0)
        self.asset.refresh_from_db()

        result = sell(self.profile, self.asset, 10)

        self.assertTrue(result['ok'])
        self.assertIn('paper_hands', self._earned_codes())

    def test_millionaire_achievement(self):
        self.profile.coins = 1_500_000
        self.profile.save()

        do_click(self.profile)

        self.assertIn('millionaire', self._earned_codes())

    def test_ten_trades(self):
        self.profile.coins = 10_000_000
        self.profile.save()
        for _ in range(10):
            buy(self.profile, self.asset, 1)

        codes = self._earned_codes()
        self.assertIn('ten_trades', codes)
        self.assertIn('first_trade', codes)

    def test_all_seeded_achievements_exist(self):
        self.assertEqual(Achievement.objects.count(), 7)

    def test_net_worth_includes_holdings(self):
        self.profile.coins = 400
        self.profile.save()
        Holding.objects.create(
            profile=self.profile,
            asset=self.asset,
            quantity=3,
            avg_price=90.0,
        )
        # 400 + 3*100 = 700
        from core import achievements as ach
        self.assertEqual(ach.net_worth(self.profile), 700.0)


class LeaderboardTest(TestCase):
    def test_ordered_by_net_worth_with_holdings(self):
        rich = make_user('rich')
        poor = make_user('poor')

        Profile.objects.filter(user=rich).update(coins=500)
        asset = make_asset(price=10.0)
        Holding.objects.create(
            profile=rich.profile,
            asset=asset,
            quantity=100,
            avg_price=5.0,
        )
        # rich: 500 + 100*10 = 1500; poor: 0

        client = Client(HTTP_HOST='localhost')
        client.force_login(poor)
        response = client.get(reverse('leaderboard'))

        self.assertEqual(response.status_code, 200)
        rows = response.context['rows']
        self.assertEqual(rows[0]['username'], 'rich')
        self.assertEqual(rows[0]['net_worth'], 1500.0)
        self.assertEqual(rows[1]['username'], 'poor')
        self.assertTrue(rows[1]['is_me'])

    def test_leaderboard_requires_login(self):
        client = Client(HTTP_HOST='localhost')
        response = client.get(reverse('leaderboard'))
        self.assertEqual(response.status_code, 302)

    def test_trade_response_contains_achievements_field(self):
        profile = make_user('tr').profile
        profile.coins = 1_000_000
        profile.save()
        asset = make_asset()

        result = buy(profile, asset, 1)

        self.assertIn('achievements', result)
