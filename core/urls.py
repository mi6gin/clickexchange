from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('game/', views.game, name='game'),
    path('market/', views.market, name='market'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api/click/', views.api_click, name='api-click'),
    path('api/buy/<int:upgrade_id>/', views.api_buy, name='api-buy'),
    path('api/state/', views.api_state, name='api-state'),
    path('api/asset/<int:asset_id>/', views.api_asset, name='api-asset'),
    path('api/portfolio/', views.api_portfolio, name='api-portfolio'),
    path(
        'api/trade/<int:asset_id>/<str:side>/',
        views.api_trade,
        name='api-trade',
    ),
]
