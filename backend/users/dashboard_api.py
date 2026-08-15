"""Staff-only, database-backed statistics for the Nuxt admin dashboard."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Episode, Movie, Series
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem
from users.admin_api import IsStaffUser, StaffAdminThrottle

User = get_user_model()

ALLOWED_PERIODS = {7, 30, 90}
VIEW_ACTIONS = ('view_movie', 'view_series')
CONTENT_ACTIONS = (*VIEW_ACTIONS, 'play', 'complete_watch')
ACTION_LABELS = {
    'view_movie': 'بازدید فیلم',
    'view_series': 'بازدید سریال',
    'view_episode': 'بازدید قسمت',
    'play': 'شروع پخش',
    'pause': 'توقف',
    'complete_watch': 'تماشای کامل',
    'like': 'پسند',
    'rate': 'امتیاز',
    'search': 'جستجو',
    'download_click': 'کلیک دانلود',
    'trailer_watch': 'تماشای تریلر',
    'add_to_watchlist': 'افزودن به فهرست',
    'filter_genre': 'فیلتر ژانر',
    'share': 'اشتراک‌گذاری',
    'open_actor_page': 'صفحه بازیگر',
}


def _comparison(current: int, previous: int):
    change_percent = None
    if previous:
        change_percent = round(((current - previous) / previous) * 100, 1)
    return {
        'current': current,
        'previous': previous,
        'change_percent': change_percent,
    }


def _rate(numerator: int, denominator: int):
    if not denominator:
        return None
    return round((numerator / denominator) * 100, 1)


def _activity_snapshot(queryset):
    snapshot = queryset.aggregate(
        tracked_views=Count('id', filter=Q(action__in=VIEW_ACTIONS)),
        playback_events=Count('id', filter=Q(action='play')),
        completed_views=Count('id', filter=Q(action='complete_watch')),
        active_users=Count('user_id', filter=Q(user_id__isnull=False), distinct=True),
        anonymous_sessions=Count(
            'session_key',
            filter=Q(user_id__isnull=True) & ~Q(session_key=''),
            distinct=True,
        ),
        download_clicks=Count('id', filter=Q(action='download_click')),
        trailer_watches=Count('id', filter=Q(action='trailer_watch')),
        searches=Count('id', filter=Q(action='search')),
    )
    snapshot['recorded_audience'] = snapshot['active_users'] + snapshot['anonymous_sessions']
    return snapshot


def _catalog_snapshot():
    movie_counts = Movie.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(is_published=True)),
        draft=Count('id', filter=Q(publication_status=Movie.PublicationStatus.DRAFT)),
        archived=Count('id', filter=Q(publication_status=Movie.PublicationStatus.ARCHIVED)),
        featured=Count('id', filter=Q(is_featured=True, is_published=True)),
        media_ready=Count('id', filter=Q(media_status='ready')),
        media_missing=Count('id', filter=Q(media_status='missing')),
        media_error=Count('id', filter=Q(media_status__in=('error', 'failed'))),
        recorded_views=Sum('view_count'),
    )
    series_counts = Series.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(is_published=True)),
        draft=Count('id', filter=Q(is_published=False)),
        featured=Count('id', filter=Q(is_featured=True, is_published=True)),
        recorded_views=Sum('view_count'),
    )
    episode_counts = Episode.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(is_published=True)),
        draft=Count('id', filter=Q(is_published=False)),
        recorded_views=Sum('view_count'),
    )

    for counts in (movie_counts, series_counts, episode_counts):
        counts['recorded_views'] = int(counts['recorded_views'] or 0)

    return {
        'movies': movie_counts,
        'series': series_counts,
        'episodes': episode_counts,
    }


def _user_snapshot():
    return User.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        verified=Count('id', filter=Q(is_verified=True)),
        staff=Count('id', filter=Q(is_staff=True)),
    )


def _daily_trend(events, users, start_date, days, current_tz):
    event_rows = {
        row['day']: row
        for row in (
            events
            .annotate(day=TruncDate('created_at', tzinfo=current_tz))
            .values('day')
            .annotate(
                tracked_views=Count('id', filter=Q(action__in=VIEW_ACTIONS)),
                playback_events=Count('id', filter=Q(action='play')),
                completed_views=Count('id', filter=Q(action='complete_watch')),
                active_users=Count(
                    'user_id',
                    filter=Q(user_id__isnull=False),
                    distinct=True,
                ),
                anonymous_sessions=Count(
                    'session_key',
                    filter=Q(user_id__isnull=True) & ~Q(session_key=''),
                    distinct=True,
                ),
            )
        )
    }
    user_rows = {
        row['day']: row['new_users']
        for row in (
            users
            .annotate(day=TruncDate('date_joined', tzinfo=current_tz))
            .values('day')
            .annotate(new_users=Count('id'))
        )
    }

    result = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        event_row = event_rows.get(day, {})
        active_users = event_row.get('active_users', 0)
        anonymous_sessions = event_row.get('anonymous_sessions', 0)
        result.append({
            'date': day.isoformat(),
            'tracked_views': event_row.get('tracked_views', 0),
            'playback_events': event_row.get('playback_events', 0),
            'completed_views': event_row.get('completed_views', 0),
            'active_users': active_users,
            'recorded_audience': active_users + anonymous_sessions,
            'new_users': user_rows.get(day, 0),
        })
    return result


def _top_content(events, limit=12):
    rows = list(
        events
        .filter(
            content_type__in=('movie', 'series'),
            object_id__isnull=False,
            action__in=CONTENT_ACTIONS,
        )
        .values('content_type', 'object_id')
        .annotate(
            activity=Count('id'),
            tracked_views=Count('id', filter=Q(action__in=VIEW_ACTIONS)),
            playback_events=Count('id', filter=Q(action='play')),
            completed_views=Count('id', filter=Q(action='complete_watch')),
        )
        .order_by('-activity', '-tracked_views', 'content_type', 'object_id')[:limit]
    )

    movie_ids = [row['object_id'] for row in rows if row['content_type'] == 'movie']
    series_ids = [row['object_id'] for row in rows if row['content_type'] == 'series']
    movies = Movie.objects.in_bulk(movie_ids)
    series = Series.objects.in_bulk(series_ids)

    result = []
    for row in rows:
        item = movies.get(row['object_id']) if row['content_type'] == 'movie' else series.get(row['object_id'])
        result.append({
            **row,
            'title': item.title if item else 'عنوان حذف‌شده',
            'slug': item.slug if item else '',
            'is_published': bool(item and item.is_published),
            'view_count': int(getattr(item, 'view_count', 0) or 0),
        })
    return result


def _top_searches(events, limit=12):
    return list(
        events
        .filter(action='search', content_type='search')
        .exclude(query='')
        .values('query')
        .annotate(
            count=Count('id'),
            zero_result_count=Count('id', filter=Q(metadata__result_count=0)),
        )
        .order_by('-count', 'query')[:limit]
    )


def _action_breakdown(events, limit=12):
    rows = list(
        events
        .values('action')
        .annotate(count=Count('id'))
        .order_by('-count', 'action')[:limit]
    )
    return [
        {
            'action': row['action'],
            'label': ACTION_LABELS.get(row['action'], row['action']),
            'count': row['count'],
        }
        for row in rows
    ]


def _device_breakdown(events):
    rows = list(
        events
        .exclude(device_type='')
        .values('device_type')
        .annotate(count=Count('id'))
        .order_by('-count', 'device_type')[:8]
    )
    unknown = events.filter(Q(device_type='') | Q(device_type__isnull=True)).count()
    result = [{'device': row['device_type'], 'count': row['count']} for row in rows]
    if unknown:
        result.append({'device': 'unknown', 'count': unknown})
    return result


def _hourly_distribution(events, current_tz):
    rows = {
        int(row['hour']): row['count']
        for row in (
            events
            .annotate(hour=ExtractHour('created_at', tzinfo=current_tz))
            .values('hour')
            .annotate(count=Count('id'))
        )
        if row['hour'] is not None
    }
    return [{'hour': hour, 'count': rows.get(hour, 0)} for hour in range(24)]


def _catalog_health():
    movies_missing_poster = Movie.objects.filter(
        Q(poster='') | Q(poster__isnull=True),
        poster_external_url='',
        poster_path='',
        is_published=True,
    ).count()
    movies_not_ready = Movie.objects.filter(
        is_published=True,
    ).exclude(media_status='ready').count()
    movies_draft = Movie.objects.filter(
        publication_status=Movie.PublicationStatus.DRAFT,
    ).count()
    series_draft = Series.objects.filter(is_published=False).count()
    movies_rights_pending = Movie.objects.filter(
        is_published=False,
        rights_verified=False,
        publication_status=Movie.PublicationStatus.DRAFT,
    ).count()

    alerts = []
    if movies_not_ready:
        alerts.append({
            'code': 'movies_media_not_ready',
            'severity': 'warning',
            'count': movies_not_ready,
            'message': 'فیلم منتشرشده بدون رسانهٔ آماده',
            'href': '/admin/movies?media_status=missing',
        })
    if movies_missing_poster:
        alerts.append({
            'code': 'movies_missing_poster',
            'severity': 'warning',
            'count': movies_missing_poster,
            'message': 'فیلم منتشرشده بدون پوستر',
            'href': '/admin/movies',
        })
    if movies_draft:
        alerts.append({
            'code': 'movies_draft',
            'severity': 'info',
            'count': movies_draft,
            'message': 'پیش‌نویس فیلم در صف انتشار',
            'href': '/admin/movies?status=draft',
        })
    if series_draft:
        alerts.append({
            'code': 'series_draft',
            'severity': 'info',
            'count': series_draft,
            'message': 'سریال منتشرنشده',
            'href': '/admin/series',
        })
    if movies_rights_pending:
        alerts.append({
            'code': 'movies_rights_pending',
            'severity': 'info',
            'count': movies_rights_pending,
            'message': 'پیش‌نویس بدون تأیید حقوق',
            'href': '/admin/movies?status=draft',
        })

    return {
        'movies_missing_poster': movies_missing_poster,
        'movies_media_not_ready': movies_not_ready,
        'movies_draft': movies_draft,
        'series_draft': series_draft,
        'movies_rights_pending': movies_rights_pending,
        'alert_count': len(alerts),
        'alerts': alerts,
    }


def _watchparty_snapshot(start, end):
    try:
        from apps.watchparty.models import WatchRoom
    except Exception:  # noqa: BLE001 — keep dashboard resilient if app is unavailable
        return {
            'available': False,
            'total': 0,
            'active': 0,
            'created_in_period': 0,
            'ended_in_period': 0,
        }

    return {
        'available': True,
        'total': WatchRoom.objects.count(),
        'active': WatchRoom.objects.filter(status=WatchRoom.Status.ACTIVE).count(),
        'created_in_period': WatchRoom.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
        ).count(),
        'ended_in_period': WatchRoom.objects.filter(
            status=WatchRoom.Status.ENDED,
            created_at__gte=start,
            created_at__lte=end,
        ).count(),
    }


def _top_genres(events, limit=8):
    return list(
        events
        .filter(action='filter_genre')
        .exclude(query='')
        .values('query')
        .annotate(count=Count('id'))
        .order_by('-count', 'query')[:limit]
    )


def _funnel(current, previous):
    current_views = current['tracked_views']
    previous_views = previous['tracked_views']
    return {
        'view_to_play': {
            'current': _rate(current['playback_events'], current_views),
            'previous': _rate(previous['playback_events'], previous_views),
        },
        'play_to_complete': {
            'current': _rate(current['completed_views'], current['playback_events']),
            'previous': _rate(previous['completed_views'], previous['playback_events']),
        },
        'view_to_complete': {
            'current': _rate(current['completed_views'], current_views),
            'previous': _rate(previous['completed_views'], previous_views),
        },
        'stages': [
            {'key': 'tracked_views', 'label': 'بازدید', 'count': current_views},
            {'key': 'playback_events', 'label': 'شروع پخش', 'count': current['playback_events']},
            {'key': 'completed_views', 'label': 'تماشای کامل', 'count': current['completed_views']},
        ],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_dashboard(request):
    try:
        requested_days = int(request.query_params.get('days', 30))
    except (TypeError, ValueError):
        requested_days = 30
    days = requested_days if requested_days in ALLOWED_PERIODS else 30

    current_tz = timezone.get_current_timezone()
    now = timezone.now()
    local_now = timezone.localtime(now, current_tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    start = local_start
    end = now
    previous_end = start
    previous_start = previous_end - (end - start)

    current_events = UserActivityEvent.objects.filter(created_at__gte=start, created_at__lte=end)
    previous_events = UserActivityEvent.objects.filter(
        created_at__gte=previous_start,
        created_at__lt=previous_end,
    )
    current_users = User.objects.filter(date_joined__gte=start, date_joined__lte=end)
    previous_users = User.objects.filter(
        date_joined__gte=previous_start,
        date_joined__lt=previous_end,
    )

    current_activity = _activity_snapshot(current_events)
    previous_activity = _activity_snapshot(previous_events)
    new_users = current_users.count()
    previous_new_users = previous_users.count()

    rating_summary = Rating.objects.aggregate(total=Count('id'), average=Avg('score'))
    event_total = UserActivityEvent.objects.count()
    period_event_total = current_events.count()
    identified_period_events = current_events.filter(user_id__isnull=False).count()
    anonymous_period_events = period_event_total - identified_period_events
    latest_event_at = (
        UserActivityEvent.objects
        .order_by('-created_at')
        .values_list('created_at', flat=True)
        .first()
    )

    payload = {
        'generated_at': now,
        'period': {
            'days': days,
            'start': start,
            'end': end,
            'previous_start': previous_start,
            'previous_end': previous_end,
            'timezone': str(current_tz),
            'current_day_is_partial': True,
        },
        'summary': {
            'total_users': User.objects.count(),
            'new_users': _comparison(new_users, previous_new_users),
            'active_users': _comparison(
                current_activity['active_users'],
                previous_activity['active_users'],
            ),
            'recorded_audience': _comparison(
                current_activity['recorded_audience'],
                previous_activity['recorded_audience'],
            ),
            'tracked_views': _comparison(
                current_activity['tracked_views'],
                previous_activity['tracked_views'],
            ),
            'playback_events': _comparison(
                current_activity['playback_events'],
                previous_activity['playback_events'],
            ),
            'completed_views': _comparison(
                current_activity['completed_views'],
                previous_activity['completed_views'],
            ),
            'download_clicks': _comparison(
                current_activity['download_clicks'],
                previous_activity['download_clicks'],
            ),
            'searches': _comparison(
                current_activity['searches'],
                previous_activity['searches'],
            ),
        },
        'funnel': _funnel(current_activity, previous_activity),
        'users': _user_snapshot(),
        'catalog': _catalog_snapshot(),
        'health': _catalog_health(),
        'engagement': {
            'ratings_total': rating_summary['total'],
            'ratings_in_period': Rating.objects.filter(
                created_at__gte=start,
                created_at__lte=end,
            ).count(),
            'average_rating': (
                round(float(rating_summary['average']), 1)
                if rating_summary['average'] is not None else None
            ),
            'likes_total': Like.objects.count(),
            'likes_in_period': Like.objects.filter(
                created_at__gte=start,
                created_at__lte=end,
            ).count(),
            'watchlist_total': WatchlistItem.objects.count(),
            'watchlist_in_period': WatchlistItem.objects.filter(
                created_at__gte=start,
                created_at__lte=end,
            ).count(),
            'favorites_total': WatchlistItem.objects.filter(
                list_type=WatchlistItem.ListType.FAVORITE,
            ).count(),
            'download_clicks_in_period': current_activity['download_clicks'],
            'trailer_watches_in_period': current_activity['trailer_watches'],
        },
        'trend': _daily_trend(
            current_events,
            current_users,
            local_start.date(),
            days,
            current_tz,
        ),
        'hourly': _hourly_distribution(current_events, current_tz),
        'actions': _action_breakdown(current_events),
        'devices': _device_breakdown(current_events),
        'top_content': _top_content(current_events),
        'top_searches': _top_searches(current_events),
        'top_genres': _top_genres(current_events),
        'watchparty': _watchparty_snapshot(start, end),
        'tracking': {
            'events_total': event_total,
            'events_in_period': period_event_total,
            'identified_events_in_period': identified_period_events,
            'anonymous_events_in_period': anonymous_period_events,
            'identified_users_in_period': current_activity['active_users'],
            'anonymous_sessions_in_period': current_events.filter(
                user_id__isnull=True,
            ).exclude(session_key='').values('session_key').distinct().count(),
            'latest_event_at': latest_event_at,
            'source': 'server_database',
            'scope': 'recorded_events_only',
            'consent_required': True,
        },
    }
    response = Response(payload)
    response['Cache-Control'] = 'private, no-store'
    return response
