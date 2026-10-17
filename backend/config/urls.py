from django.contrib import admin
from django.urls import path, register_converter
from config.converters import UnicodeSlugConverter

register_converter(UnicodeSlugConverter, 'uslug')

from apps.accounts.api import (
    confirm_password_reset, login_user, logout_user, me, register,
    request_password_reset, token_refresh,
)
from users.admin_api import admin_user_detail, admin_user_list_create
from users.analytics_api import (
    analytics_behavior,
    analytics_content_top,
    analytics_downloads,
    analytics_engagement,
    analytics_overview,
    analytics_presence,
    analytics_users,
)
from users.dashboard_api import insights_dashboard
from apps.catalog.indexnow import indexnow_key_file
from apps.catalog.sitemap_api import catalog_sitemap
from apps.catalog.api import (
    anime_catalog, catalog_filters, imdb_top250, collection_detail, collection_list, recent_catalog,
    actor_detail, actor_list, country_list, director_detail, director_list,
    genre_list, home_rails, home_slider, movie_detail, movie_list, movie_similar,
    content_issue_options, content_issue_status, playback_failure_report, playback_subtitle_ensure,
    playback_subtitle_status, report_content_issue,
    search_content, search_suggest, series_detail, series_list, series_similar,
    subtitle_sync_report, trending, weekly_schedule,
)
from apps.catalog.playback_api import playback_resolve
from apps.catalog.region_api import playback_region
from apps.catalog.stream_api import (
    stream_open, stream_playlist, stream_segment, stream_status,
)
from apps.catalog.admin_api import (
    admin_movie_detail, admin_movie_list_create,
    admin_series_detail, admin_series_list_create,
    admin_slider_list, admin_slider_reorder,
    catalog_importer_settings,
    catalog_sync_run_cancel, catalog_sync_run_detail, catalog_sync_run_list_create,
    movie_sync_tmdb, series_sync_tmdb,
    tmdb_movie_import, tmdb_movie_preview, tmdb_search,
    tmdb_series_import, tmdb_series_preview,
)
from apps.catalog.admin_ops import (
    audit_feed, bulk_action, catalog_health, content_reports_purge, media_desk, ops_overview,
)
from apps.catalog.taxonomy_api import (
    admin_actor_detail, admin_actor_list_create,
    admin_country_detail, admin_country_list_create,
    admin_director_detail, admin_director_list_create,
    admin_genre_detail, admin_genre_list_create,
    admin_tag_detail, admin_tag_list_create,
)
from apps.catalog.archive_api import (
    archive_asset_delete, archive_asset_download_url, archive_asset_status,
    archive_upload_abort, archive_upload_complete, archive_upload_initiate,
    archive_upload_presign_parts,
)
from apps.catalog.provider_import.api import (
    catalog_year_import_start,
    movie_provider_crawl_downloads,
    movie_provider_discover,
    provider_import_job_approve_match,
    provider_import_job_cancel,
    provider_import_job_candidates,
    provider_import_job_detail,
    provider_import_job_import_selected,
    provider_import_job_items,
    provider_import_job_list,
    provider_import_job_logs,
    provider_source_detail,
    provider_source_discover,
    provider_source_import,
    provider_source_list_create,
    provider_source_validate,
    series_provider_crawl_downloads,
    series_provider_discover,
)
from apps.engagement.api import (
    community_messages, create_event, create_privacy_safe_event, like_toggle, likes_list, rate_content, rating_summary,
    support_ticket_detail, support_ticket_list_create, watch_stats, watchlist_list, watchlist_toggle,
)
from apps.engagement.admin_api import (
    admin_interaction_overview, admin_review_detail, admin_reviews_list,
    admin_support_inbox, admin_support_ticket_detail, admin_support_tickets_purge,
)
from apps.engagement.collections_api import (
    collections_root,
    collection_detail as my_collection_detail,
    collection_items,
    collection_reorder,
    collections_containing,
    public_collection,
    public_collection_by_token,
    public_collections_containing,
    public_profile,
)
from apps.recommendations.api import recommendations
from apps.assistant.api import assistant_chat, assistant_insight
from apps.watchparty.api import (
    create_room, end_room, get_room, join_room, leave_room, recent_messages,
)
from config.api import health_check
from config.app_release import app_version

urlpatterns = [
    path('api/health/', health_check, name='health_check'),
    # The sideloaded Android app's update channel — Play's In-App Updates
    # API is unusable for an APK we host ourselves. See config/app_release.py.
    path('api/app/version/', app_version, name='app_version'),
    path('api/auth/register/', register, name='auth_register'),
    path('api/auth/token/', login_user, name='token_obtain_pair'),
    path('api/auth/token/refresh/', token_refresh, name='token_refresh'),
    path('api/auth/logout/', logout_user, name='auth_logout'),
    path('api/auth/password-reset/', request_password_reset, name='auth_password_reset'),
    path('api/auth/password-reset/confirm/', confirm_password_reset, name='auth_password_reset_confirm'),
    path('api/accounts/me/', me, name='accounts_me'),
    path('api/recommendations/', recommendations, name='recommendations'),
    path('api/assistant/chat/', assistant_chat, name='assistant_chat'),
    path('api/assistant/insight/', assistant_insight, name='assistant_insight'),
    path('api/watch-party/rooms/', create_room, name='watchparty_create_room'),
    path('api/watch-party/rooms/<str:invite_code>/', get_room, name='watchparty_room'),
    path('api/watch-party/rooms/<str:invite_code>/join/', join_room, name='watchparty_join'),
    path('api/watch-party/rooms/<str:invite_code>/leave/', leave_room, name='watchparty_leave'),
    path('api/watch-party/rooms/<str:invite_code>/messages/', recent_messages, name='watchparty_messages'),
    path('api/watch-party/rooms/<str:invite_code>/end/', end_room, name='watchparty_end'),
    path('api/catalog/recent/', recent_catalog, name='catalog_recent'),
    path('api/catalog/schedule/', weekly_schedule, name='catalog_schedule'),
    path('api/catalog/anime/', anime_catalog, name='catalog_anime'),
    path('api/catalog/top250/', imdb_top250, name='catalog_top250'),
    path('api/catalog/sitemap/', catalog_sitemap, name='catalog_sitemap'),
    path('api/catalog/indexnow-key/', indexnow_key_file, name='catalog_indexnow_key'),
    path('api/catalog/filters/', catalog_filters, name='catalog_filters'),
    path('api/catalog/playback-subtitle-ensure/', playback_subtitle_ensure, name='playback_subtitle_ensure'),
    path('api/catalog/playback-subtitle-status/', playback_subtitle_status, name='playback_subtitle_status'),
    path('api/catalog/subtitle-sync/report/', subtitle_sync_report, name='subtitle_sync_report'),
    path('api/catalog/report-issue/', report_content_issue, name='report_content_issue'),
    path('api/catalog/report-issue/status/', content_issue_status, name='content_issue_status'),
    path('api/catalog/playback-failure/', playback_failure_report, name='playback_failure_report'),
    # The button catalogue itself, so a new repair becomes a new button in
    # every client without an app release.
    path('api/catalog/report-issue/options/', content_issue_options, name='content_issue_options'),
    # Playback gateway — the fallback path for sources a browser cannot open
    # directly. The segment route is matched loosely here and validated against
    # an exact-match pattern inside the gateway.
    # Asked once per play, before the source is used at all: most provider
    # links here carry a token that lapses in hours, so the URL the page was
    # rendered with is not necessarily the URL that plays.
    path('api/playback/resolve/', playback_resolve, name='playback_resolve'),
    path('api/playback/region/', playback_region, name='playback_region'),
    path('api/stream/open/', stream_open, name='stream_open'),
    path('api/stream/status/', stream_status, name='stream_status'),
    path('api/stream/<str:session>/index.m3u8', stream_playlist, name='stream_playlist'),
    path('api/stream/<str:session>/<str:name>', stream_segment, name='stream_segment'),
    path('api/movies/', movie_list, name='movie_list'),
    path('api/movies/<uslug:slug>/', movie_detail, name='movie_detail'),
    path('api/movies/<uslug:slug>/similar/', movie_similar, name='movie_similar'),
    path('api/analytics/insights/', insights_dashboard, name='analytics_insights'),
    path('api/analytics/overview/', analytics_overview, name='analytics_overview'),
    path('api/analytics/users/', analytics_users, name='analytics_users'),
    path('api/analytics/content/top/', analytics_content_top, name='analytics_content_top'),
    path('api/analytics/downloads/', analytics_downloads, name='analytics_downloads'),
    path('api/analytics/engagement/', analytics_engagement, name='analytics_engagement'),
    path('api/analytics/behavior/', analytics_behavior, name='analytics_behavior'),
    path('api/analytics/presence/', analytics_presence, name='analytics_presence'),
    path('api/series/', series_list, name='series_list'),
    path('api/series/<uslug:slug>/', series_detail, name='series_detail'),
    path('api/series/<uslug:slug>/similar/', series_similar, name='series_similar'),
    path('api/genres/', genre_list, name='genre_list'),
    path('api/home/rails/', home_rails, name='home_rails'),
    path('api/home/slider/', home_slider, name='home_slider'),
    path('api/countries/', country_list, name='country_list'),
    path('api/actors/', actor_list, name='actor_list'),
    path('api/actors/<uslug:slug>/', actor_detail, name='actor_detail'),
    path('api/directors/', director_list, name='director_list'),
    path('api/directors/<uslug:slug>/', director_detail, name='director_detail'),
    path('api/collections/', collection_list, name='collection_list'),
    path('api/collections/<uslug:slug>/', collection_detail, name='collection_detail'),
    path('api/search/', search_content, name='search_content'),
    path('api/search/suggest/', search_suggest, name='search_suggest'),
    path('api/trending/', trending, name='trending'),
    path('api/events/', create_privacy_safe_event, name='create_privacy_safe_event'),
    path('api/engagement/events/', create_event, name='create_event'),
    path('api/engagement/ratings/', rate_content, name='rate_content'),
    path('api/engagement/ratings/summary/', rating_summary, name='rating_summary'),
    path('api/engagement/watchlist/', watchlist_list, name='watchlist_list'),
    path('api/engagement/watchlist/toggle/', watchlist_toggle, name='watchlist_toggle'),
    path('api/engagement/likes/', likes_list, name='likes_list'),
    path('api/engagement/likes/toggle/', like_toggle, name='like_toggle'),
    path('api/engagement/watch-stats/', watch_stats, name='watch_stats'),
    # --- User collections ("کالکشن") + public profiles ---
    path('api/engagement/collections/', collections_root, name='my_collections'),
    path('api/engagement/collections/containing/', collections_containing, name='collections_containing'),
    path('api/engagement/collections/public-containing/', public_collections_containing, name='public_collections_containing'),
    path('api/engagement/collections/<uslug:slug>/', my_collection_detail, name='my_collection_detail'),
    path('api/engagement/collections/<uslug:slug>/items/', collection_items, name='my_collection_items'),
    path('api/engagement/collections/<uslug:slug>/reorder/', collection_reorder, name='my_collection_reorder'),
    path('api/share/collection/<str:token>/', public_collection_by_token, name='public_collection_by_token'),
    path('api/users/<str:username>/', public_profile, name='public_profile'),
    path('api/users/<str:username>/collections/<uslug:slug>/', public_collection, name='public_collection'),
    path('api/support/tickets/', support_ticket_list_create, name='support_ticket_list_create'),
    path('api/support/tickets/<str:tracking_code>/', support_ticket_detail, name='support_ticket_detail'),
    path('api/community/messages/', community_messages, name='community_messages'),

    # --- Staff admin API (Nuxt admin panel) ---
    path('api/admin/tmdb/search/', tmdb_search, name='admin_tmdb_search'),
    path('api/admin/tmdb/movie/<int:tmdb_id>/preview/', tmdb_movie_preview, name='admin_tmdb_preview'),
    path('api/admin/tmdb/movie/<int:tmdb_id>/import/', tmdb_movie_import, name='admin_tmdb_import'),
    path('api/admin/tmdb/series/<int:tmdb_id>/preview/', tmdb_series_preview, name='admin_tmdb_series_preview'),
    path('api/admin/tmdb/series/<int:tmdb_id>/import/', tmdb_series_import, name='admin_tmdb_series_import'),
    path('api/admin/movies/', admin_movie_list_create, name='admin_movie_list_create'),
    path('api/admin/movies/<int:movie_id>/', admin_movie_detail, name='admin_movie_detail'),
    path('api/admin/movies/<int:movie_id>/sync-tmdb/', movie_sync_tmdb, name='admin_movie_sync_tmdb'),
    path('api/admin/slider/', admin_slider_list, name='admin_slider_list'),
    path('api/admin/slider/reorder/', admin_slider_reorder, name='admin_slider_reorder'),
    path('api/admin/series/<int:series_id>/sync-tmdb/', series_sync_tmdb, name='admin_series_sync_tmdb'),
    path('api/admin/series/', admin_series_list_create, name='admin_series_list_create'),
    path('api/admin/series/<int:series_id>/', admin_series_detail, name='admin_series_detail'),
    path('api/admin/genres/', admin_genre_list_create, name='admin_genre_list_create'),
    path('api/admin/genres/<int:pk>/', admin_genre_detail, name='admin_genre_detail'),
    path('api/admin/countries/', admin_country_list_create, name='admin_country_list_create'),
    path('api/admin/countries/<int:pk>/', admin_country_detail, name='admin_country_detail'),
    path('api/admin/tags/', admin_tag_list_create, name='admin_tag_list_create'),
    path('api/admin/tags/<int:pk>/', admin_tag_detail, name='admin_tag_detail'),
    path('api/admin/actors/', admin_actor_list_create, name='admin_actor_list_create'),
    path('api/admin/actors/<int:pk>/', admin_actor_detail, name='admin_actor_detail'),
    path('api/admin/directors/', admin_director_list_create, name='admin_director_list_create'),
    path('api/admin/directors/<int:pk>/', admin_director_detail, name='admin_director_detail'),
    path('api/admin/users/', admin_user_list_create, name='admin_user_list_create'),
    path('api/admin/users/<int:user_id>/', admin_user_detail, name='admin_user_detail'),
    path('api/admin/catalog-sync/runs/', catalog_sync_run_list_create, name='admin_catalog_sync_runs'),
    path('api/admin/catalog-sync/settings/', catalog_importer_settings, name='admin_catalog_importer_settings'),
    path('api/admin/catalog-sync/runs/<int:run_id>/', catalog_sync_run_detail, name='admin_catalog_sync_run'),
    path('api/admin/catalog-sync/runs/<int:run_id>/cancel/', catalog_sync_run_cancel, name='admin_catalog_sync_cancel'),
    path('api/admin/archive/uploads/initiate/', archive_upload_initiate, name='admin_archive_upload_initiate'),
    path('api/admin/archive/uploads/<uuid:asset_id>/presign-parts/', archive_upload_presign_parts, name='admin_archive_presign_parts'),
    path('api/admin/archive/uploads/<uuid:asset_id>/complete/', archive_upload_complete, name='admin_archive_complete'),
    path('api/admin/archive/uploads/<uuid:asset_id>/abort/', archive_upload_abort, name='admin_archive_abort'),
    path('api/admin/archive/assets/<uuid:asset_id>/status/', archive_asset_status, name='admin_archive_status'),
    path('api/admin/archive/assets/<uuid:asset_id>/download-url/', archive_asset_download_url, name='admin_archive_download_url'),
    path('api/admin/archive/assets/<uuid:asset_id>/delete/', archive_asset_delete, name='admin_archive_delete'),
    path('api/admin/provider-sources/', provider_source_list_create, name='admin_provider_sources'),
    path('api/admin/provider-sources/<int:provider_id>/', provider_source_detail, name='admin_provider_source'),
    path('api/admin/provider-sources/<int:provider_id>/validate/', provider_source_validate, name='admin_provider_validate'),
    path('api/admin/provider-sources/<int:provider_id>/discover/', provider_source_discover, name='admin_provider_discover'),
    path('api/admin/provider-sources/<int:provider_id>/import/', provider_source_import, name='admin_provider_import'),
    path('api/admin/catalog/movies/<int:movie_id>/provider-discover/', movie_provider_discover, name='admin_movie_provider_discover'),
    path('api/admin/catalog/movies/<int:movie_id>/provider-crawl-downloads/', movie_provider_crawl_downloads, name='admin_movie_provider_crawl_downloads'),
    path('api/admin/catalog/series/<int:series_id>/provider-discover/', series_provider_discover, name='admin_series_provider_discover'),
    path('api/admin/catalog/series/<int:series_id>/provider-crawl-downloads/', series_provider_crawl_downloads, name='admin_series_provider_crawl_downloads'),
    path('api/admin/provider-import/catalog-year/start/', catalog_year_import_start, name='admin_catalog_year_import_start'),
    path('api/admin/provider-import/jobs/', provider_import_job_list, name='admin_provider_import_jobs'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/', provider_import_job_detail, name='admin_provider_import_job'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/cancel/', provider_import_job_cancel, name='admin_provider_import_cancel'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/approve-match/', provider_import_job_approve_match, name='admin_provider_import_approve'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/import/', provider_import_job_import_selected, name='admin_provider_import_selected'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/items/', provider_import_job_items, name='admin_provider_import_items'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/candidates/', provider_import_job_candidates, name='admin_provider_import_candidates'),
    path('api/admin/provider-import/jobs/<uuid:job_id>/logs/', provider_import_job_logs, name='admin_provider_import_logs'),
    # --- Operations desk: per-title media control, bulk verbs, health queues ---
    path('api/admin/catalog/<str:kind>/<int:object_id>/media/', media_desk, name='admin_media_desk'),
    path('api/admin/catalog/bulk/', bulk_action, name='admin_catalog_bulk'),
    path('api/admin/catalog/health/', catalog_health, name='admin_catalog_health'),
    path('api/admin/catalog/reports/purge/', content_reports_purge, name='admin_content_reports_purge'),
    path('api/admin/ops/overview/', ops_overview, name='admin_ops_overview'),
    path('api/admin/audit/', audit_feed, name='admin_audit_feed'),
    path('api/admin/interaction-overview/', admin_interaction_overview, name='admin_interaction_overview'),
    path('api/admin/reviews/', admin_reviews_list, name='admin_reviews_list'),
    path('api/admin/reviews/<int:rating_id>/', admin_review_detail, name='admin_review_detail'),
    path('api/admin/support/tickets/', admin_support_inbox, name='admin_support_inbox'),
    path('api/admin/support/tickets/purge/', admin_support_tickets_purge, name='admin_support_tickets_purge'),
    path('api/admin/support/tickets/<str:tracking_code>/', admin_support_ticket_detail, name='admin_support_ticket_detail'),
]
