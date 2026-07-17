from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.api import (
    confirm_password_reset, login_user, logout_user, me, register, request_password_reset,
)
from apps.catalog.api import (
    actor_detail, actor_list, director_detail, director_list,
    genre_list, movie_detail, movie_list, search_content,
    series_detail, series_list, trending,
)
from apps.engagement.api import (
    create_event, create_privacy_safe_event, like_toggle, rate_content, rating_summary,
    watchlist_list, watchlist_toggle,
)
from apps.recommendations.api import recommendations
from apps.watchparty.api import (
    create_room, end_room, get_room, join_room, leave_room, recent_messages,
)
from config.api import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/auth/register/', register, name='auth_register'),
    path('api/auth/token/', login_user, name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', logout_user, name='auth_logout'),
    path('api/auth/password-reset/', request_password_reset, name='auth_password_reset'),
    path('api/auth/password-reset/confirm/', confirm_password_reset, name='auth_password_reset_confirm'),
    path('api/accounts/me/', me, name='accounts_me'),
    path('api/recommendations/', recommendations, name='recommendations'),
    path('api/watch-party/rooms/', create_room, name='watchparty_create_room'),
    path('api/watch-party/rooms/<str:invite_code>/', get_room, name='watchparty_room'),
    path('api/watch-party/rooms/<str:invite_code>/join/', join_room, name='watchparty_join'),
    path('api/watch-party/rooms/<str:invite_code>/leave/', leave_room, name='watchparty_leave'),
    path('api/watch-party/rooms/<str:invite_code>/messages/', recent_messages, name='watchparty_messages'),
    path('api/watch-party/rooms/<str:invite_code>/end/', end_room, name='watchparty_end'),
    path('api/movies/', movie_list, name='movie_list'),
    path('api/movies/<slug:slug>/', movie_detail, name='movie_detail'),
    path('api/series/', series_list, name='series_list'),
    path('api/series/<slug:slug>/', series_detail, name='series_detail'),
    path('api/genres/', genre_list, name='genre_list'),
    path('api/actors/', actor_list, name='actor_list'),
    path('api/actors/<slug:slug>/', actor_detail, name='actor_detail'),
    path('api/directors/', director_list, name='director_list'),
    path('api/directors/<slug:slug>/', director_detail, name='director_detail'),
    path('api/search/', search_content, name='search_content'),
    path('api/trending/', trending, name='trending'),
    path('api/events/', create_privacy_safe_event, name='create_privacy_safe_event'),
    path('api/engagement/events/', create_event, name='create_event'),
    path('api/engagement/ratings/', rate_content, name='rate_content'),
    path('api/engagement/ratings/summary/', rating_summary, name='rating_summary'),
    path('api/engagement/watchlist/', watchlist_list, name='watchlist_list'),
    path('api/engagement/watchlist/toggle/', watchlist_toggle, name='watchlist_toggle'),
    path('api/engagement/likes/toggle/', like_toggle, name='like_toggle'),
]
