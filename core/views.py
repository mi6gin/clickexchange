import json

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import broker, services
from core import generator
from core import market as market_engine
from core.models import Asset, Profile, Transaction, Upgrade


def home(request):
    if request.user.is_authenticated:
        return redirect('game')
    return render(request, 'core/home.html')


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(
                request,
                user,
                backend='django.contrib.auth.backends.ModelBackend',
            )
            return redirect('game')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def _profile(request) -> Profile:
    return request.user.profile


@login_required
def game(request):
    profile = _profile(request)
    services.sync_profile(profile)

    upgrades = []
    for upgrade in Upgrade.objects.all().order_by('base_cost'):
        cost = services.upgrade_cost(profile, upgrade)
        upgrades.append({
            'id': upgrade.id,
            'kind': upgrade.kind,
            'name': upgrade.get_kind_display(),
            'level': services.get_level(profile, upgrade.kind),
            'cost': cost,
            'maxed': cost is None,
        })

    context = {
        'profile': profile,
        'stats': services.stats(profile),
        'upgrades': upgrades,
    }
    return render(request, 'core/game.html', context)


@login_required
@require_POST
def api_click(request):
    result = services.do_click(_profile(request))
    status = 200 if result['ok'] else 400
    return JsonResponse(result, status=status)


@login_required
@require_POST
def api_buy(request, upgrade_id: int):
    upgrade = get_object_or_404(Upgrade, id=upgrade_id)
    result = services.buy_upgrade(_profile(request), upgrade)
    status = 200 if result['ok'] else 400
    return JsonResponse(result, status=status)


@login_required
def api_state(request):
    profile = _profile(request)
    services.sync_profile(profile)
    data = {
        'coins': profile.coins,
        'energy': profile.effective_energy(),
        'total_clicks': profile.total_clicks,
        **services.stats(profile),
    }
    return JsonResponse(data)


# ---------- Биржа ----------


@login_required
def market(request):
    profile = _profile(request)
    services.sync_profile(profile)
    ipo = generator.maybe_run_ipo()

    assets = []
    for asset in Asset.objects.all().order_by('ticker'):
        state = market_engine.market_state(asset)
        assets.append(state)

    context = {
        'profile': profile,
        'assets': assets,
        'ipo': ipo,
        'portfolio': broker.portfolio_summary(profile),
        'trades': profile.trades.select_related('asset')[:10],
    }
    return render(request, 'core/market.html', context)


@login_required
def api_asset(request, asset_id: int):
    asset = get_object_or_404(Asset, id=asset_id)
    return JsonResponse(market_engine.market_state(asset))


@login_required
def api_portfolio(request):
    profile = _profile(request)
    return JsonResponse(broker.portfolio_summary(profile))


@login_required
@require_POST
def api_trade(request, asset_id: int, side: str):
    if side not in ('buy', 'sell'):
        return JsonResponse({'ok': False, 'error': 'invalid_side'}, status=400)

    try:
        payload = json.loads(request.body or b'{}')
        quantity = int(payload.get('quantity', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'invalid_quantity'}, status=400)

    asset = get_object_or_404(Asset, id=asset_id)
    profile = _profile(request)

    if side == 'buy':
        result = broker.buy(profile, asset, quantity)
    else:
        result = broker.sell(profile, asset, quantity)

    status = 200 if result['ok'] else 400
    result['portfolio'] = broker.portfolio_summary(profile)
    return JsonResponse(result, status=status)

