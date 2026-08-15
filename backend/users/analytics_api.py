"""Staff-only analytics APIs backed by live Postgres data.

Primary sources (real DB):
  - auth users (signups / last_login)
  - catalog Movie / Series / Episode
  - watch-party rooms & playback state
  - likes / ratings / watchlist
  - UserActivityEvent when present (engagement tracker)

Contract:
  GET /api/analytics/overview/
  GET /api/analytics/users/?period=30d
  GET /api/analytics/content/top/
  GET /api/analytics/engagement/
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.catalog.models import Episode, Movie, Series
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem
from users.admin_api import IsStaffUser, StaffAdminThrottle
from users.dashboard_api import VIEW_ACTIONS, _comparison, _device_breakdown, _rate, _top_searches
from users.presence import PRESENCE_WINDOW_SECONDS, touch_presence

User = get_user_model()

PERIOD_ALIASES = {
    '7d': 7,
    '7': 7,
    '30d': 30,
    '30': 30,
    '90d': 90,
    '90': 90,
}
ALLOWED_DAYS = {7, 30, 90}
WEEKDAY_LABELS_FA = {
    1: 'یکشنبه',
    2: 'دوشنبه',
    3: 'سه‌شنبه',
    4: 'چهارشنبه',
    5: 'پنجشنبه',
    6: 'جمعه',
    7: 'شنبه',
}


def _parse_period(request) -> int:
    raw = str(request.query_params.get('period') or request.query_params.get('days') or '30d').strip().lower()
    if raw in PERIOD_ALIASES:
        return PERIOD_ALIASES[raw]
    try:
        days = int(raw.rstrip('d'))
    except (TypeError, ValueError):
        return 30
    return days if days in ALLOWED_DAYS else 30


def _window(days: int):
    current_tz = timezone.get_current_timezone()
    now = timezone.now()
    local_now = timezone.localtime(now, current_tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    start = local_start
    end = now
    previous_end = start
    previous_start = previous_end - (end - start)
    return {
        'tz': current_tz,
        'now': now,
        'local_now': local_now,
        'start': start,
        'end': end,
        'previous_start': previous_start,
        'previous_end': previous_end,
        'days': days,
        'start_date': local_start.date(),
    }


def _envelope(data: dict[str, Any], *, days: int, now, win: dict | None = None) -> dict[str, Any]:
    payload = {
        'data': data,
        'period': {
            'days': days,
            'label': f'{days}d',
            'key': f'{days}d',
        },
        'generated_at': now.isoformat(),
        'source': 'database',
    }
    if win:
        payload['period'].update({
            'start': win['start'].isoformat(),
            'end': win['end'].isoformat(),
            'timezone': str(win['tz']),
        })
    return payload


def _watchparty_models():
    try:
        from apps.watchparty.models import WatchRoom, WatchRoomMember, WatchRoomPlaybackState
        return WatchRoom, WatchRoomMember, WatchRoomPlaybackState
    except Exception:  # noqa: BLE001
        return None, None, None


def _online_snapshot(now):
    """Realtime metrics from fresh signals only — never inflate with stale room status.

    Sources (union for authenticated online users):
      - Redis presence heartbeats (primary; ~90s TTL)
      - Watch-party member last_seen within the window
      - UserActivityEvent within the window
      - last_login within the window
    """
    from users.presence import presence_counts

    window_minutes = max(1, int(round(PRESENCE_WINDOW_SECONDS / 60)) or 1)
    # Align DB signals with the presence TTL so metrics stay consistent.
    since = now - timedelta(seconds=PRESENCE_WINDOW_SECONDS)
    WatchRoom, WatchRoomMember, Playback = _watchparty_models()

    presence = presence_counts()
    online_ids: set[int] = set(presence.get('user_ids') or set())

    event_ids = set(
        UserActivityEvent.objects.filter(
            created_at__gte=since,
            user_id__isnull=False,
        ).values_list('user_id', flat=True).distinct()
    )
    online_ids |= {int(uid) for uid in event_ids}

    login_ids = set(
        User.objects.filter(
            last_login__gte=since,
            is_active=True,
        ).values_list('id', flat=True)
    )
    online_ids |= {int(uid) for uid in login_ids}

    watchparty_ids: set[int] = set()
    live_sessions = 0
    playing_sessions = 0
    active_rooms = 0

    if WatchRoomMember is not None:
        # Fresh heartbeat only — ignore stale is_online flags on expired rooms.
        watchparty_ids = {
            int(uid)
            for uid in WatchRoomMember.objects.filter(
                last_seen_at__gte=since,
            ).values_list('user_id', flat=True).distinct()
        }
        online_ids |= watchparty_ids

    if WatchRoom is not None:
        # Housekeeping: expired rooms must not remain "active" in status.
        WatchRoom.objects.filter(
            status=WatchRoom.Status.ACTIVE,
            expires_at__lte=now,
        ).update(status=WatchRoom.Status.EXPIRED)
        if WatchRoomMember is not None:
            WatchRoomMember.objects.filter(
                is_online=True,
                last_seen_at__lt=since,
            ).update(is_online=False)

        live_room_ids: set[int] = set(
            WatchRoom.objects.filter(
                status=WatchRoom.Status.ACTIVE,
                expires_at__gt=now,
                members__last_seen_at__gte=since,
            ).values_list('id', flat=True).distinct()
        )
        if Playback is not None:
            playback_room_ids = set(
                Playback.objects.filter(
                    updated_at__gte=since,
                    room__status=WatchRoom.Status.ACTIVE,
                    room__expires_at__gt=now,
                ).values_list('room_id', flat=True)
            )
            live_room_ids |= {int(rid) for rid in playback_room_ids}
            playing_sessions = Playback.objects.filter(
                is_playing=True,
                updated_at__gte=since,
                room_id__in=live_room_ids,
            ).count() if live_room_ids else 0
            # A live session is a room with fresh playback sync in the window.
            live_sessions = Playback.objects.filter(
                updated_at__gte=since,
                room_id__in=live_room_ids,
            ).count() if live_room_ids else 0
        active_rooms = len(live_room_ids)
        if not live_sessions:
            live_sessions = active_rooms

    return {
        'online_users': len(online_ids),
        'online_guests': int(presence.get('guests') or 0),
        'online_total': len(online_ids) + int(presence.get('guests') or 0),
        'live_watch_sessions': live_sessions,
        'playing_sessions': playing_sessions,
        'active_watch_rooms': active_rooms,
        'window_minutes': window_minutes,
        'window_seconds': PRESENCE_WINDOW_SECONDS,
        'sources': {
            'presence': int(presence.get('authenticated') or 0),
            'presence_available': bool(presence.get('available')),
            'activity_events': len(event_ids),
            'recent_logins': len(login_ids),
            'watchparty': len(watchparty_ids),
        },
    }


def _watch_hours_from_db(start, end) -> float:
    """Estimate watch hours from playback state + activity progress."""
    _, _, Playback = _watchparty_models()
    hours = 0.0
    if Playback is not None:
        agg = Playback.objects.filter(updated_at__gte=start, updated_at__lte=end).aggregate(
            total_pos=Sum('position_seconds'),
            total_dur=Sum('duration_seconds'),
            count=Count('id'),
        )
        pos = float(agg['total_pos'] or 0)
        dur = float(agg['total_dur'] or 0)
        # Prefer watched position; fall back to a fraction of duration.
        seconds = pos if pos > 0 else dur * 0.35
        hours += seconds / 3600.0

    events = UserActivityEvent.objects.filter(
        created_at__gte=start,
        created_at__lte=end,
        action__in=('play', 'complete_watch', 'watch_progress', 'pause'),
    )
    plays = events.filter(action='play').count()
    completes = events.filter(action='complete_watch').count()
    hours += (plays * 12 + completes * 35) / 60.0

    WatchRoom, _, _ = _watchparty_models()
    if WatchRoom is not None and hours < 0.1:
        # Each room in period ≈ 40 minutes average session proxy.
        rooms = WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end).count()
        hours += rooms * (40 / 60.0)

    return round(hours, 1)


def _registrations_series(users_qs, *, start_date, days, tz, granularity: str):
    if granularity == 'weekly':
        rows = list(
            users_qs
            .annotate(bucket=TruncWeek('date_joined', tzinfo=tz))
            .values('bucket')
            .annotate(count=Count('id'))
            .order_by('bucket')
        )
        return [
            {
                'date': row['bucket'].date().isoformat(),
                'label': row['bucket'].date().isoformat(),
                'value': row['count'],
            }
            for row in rows
            if row['bucket'] is not None
        ]

    if granularity == 'monthly':
        rows = list(
            users_qs
            .annotate(bucket=TruncMonth('date_joined', tzinfo=tz))
            .values('bucket')
            .annotate(count=Count('id'))
            .order_by('bucket')
        )
        return [
            {
                'date': row['bucket'].date().isoformat(),
                'label': row['bucket'].date().isoformat(),
                'value': row['count'],
            }
            for row in rows
            if row['bucket'] is not None
        ]

    rows = {
        row['day']: row['count']
        for row in (
            users_qs
            .annotate(day=TruncDate('date_joined', tzinfo=tz))
            .values('day')
            .annotate(count=Count('id'))
        )
    }
    return [
        {
            'date': (start_date + timedelta(days=offset)).isoformat(),
            'label': (start_date + timedelta(days=offset)).isoformat(),
            'value': rows.get(start_date + timedelta(days=offset), 0),
        }
        for offset in range(days)
    ]


def _active_by_weekday_from_logins(start, end, tz):
    rows = {
        int(row['weekday']): row['count']
        for row in (
            User.objects.filter(last_login__gte=start, last_login__lte=end)
            .annotate(weekday=ExtractWeekDay('last_login', tzinfo=tz))
            .values('weekday')
            .annotate(count=Count('id'))
        )
        if row['weekday'] is not None
    }
    # Also fold activity events.
    event_rows = {
        int(row['weekday']): row['count']
        for row in (
            UserActivityEvent.objects.filter(created_at__gte=start, created_at__lte=end, user_id__isnull=False)
            .annotate(weekday=ExtractWeekDay('created_at', tzinfo=tz))
            .values('weekday')
            .annotate(count=Count('user_id', distinct=True))
        )
        if row['weekday'] is not None
    }
    order = [7, 1, 2, 3, 4, 5, 6]
    return [
        {
            'weekday': day,
            'label': WEEKDAY_LABELS_FA[day],
            'value': max(rows.get(day, 0), event_rows.get(day, 0)),
        }
        for day in order
    ]


def _normalize_device_breakdown(rows: list[dict]) -> list[dict]:
    buckets = {'mobile': 0, 'desktop': 0, 'tablet': 0, 'other': 0}
    for row in rows:
        raw = str(row.get('device') or '').strip().lower()
        count = int(row.get('count') or 0)
        if raw in {'mobile', 'phone', 'android', 'ios'}:
            buckets['mobile'] += count
        elif raw in {'desktop', 'web', 'pc', 'windows', 'macos', 'linux'}:
            buckets['desktop'] += count
        elif raw in {'tablet', 'ipad'}:
            buckets['tablet'] += count
        else:
            buckets['other'] += count
    labels = {
        'mobile': 'موبایل',
        'desktop': 'دسکتاپ',
        'tablet': 'تبلت',
        'other': 'سایر',
    }
    result = [
        {'id': key, 'label': labels[key], 'value': value}
        for key, value in buckets.items()
        if value or key in {'mobile', 'desktop'}
    ]
    if sum(item['value'] for item in result) == 0:
        # No device telemetry yet — report empty slices honestly.
        return [
            {'id': 'desktop', 'label': 'دسکتاپ', 'value': 0},
            {'id': 'mobile', 'label': 'موبایل', 'value': 0},
            {'id': 'tablet', 'label': 'تبلت', 'value': 0},
        ]
    return result


def _top_active_users(start, end, limit=10):
    # Prefer users with recent login; enrich with watch-party hosting & event counts.
    WatchRoom, _, _ = _watchparty_models()
    host_counts = {}
    if WatchRoom is not None:
        for row in (
            WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end)
            .values('host_user_id')
            .annotate(count=Count('id'))
        ):
            if row['host_user_id']:
                host_counts[row['host_user_id']] = row['count']

    event_rows = {
        row['user_id']: row
        for row in (
            UserActivityEvent.objects.filter(
                created_at__gte=start,
                created_at__lte=end,
                user_id__isnull=False,
            )
            .values('user_id')
            .annotate(
                events=Count('id'),
                plays=Count('id', filter=Q(action='play')),
                completes=Count('id', filter=Q(action='complete_watch')),
                last_seen=Max('created_at'),
            )
        )
    }

    candidates = {}
    for user in User.objects.filter(is_active=True).exclude(is_staff=True).order_by('-last_login', '-date_joined')[:80]:
        events = event_rows.get(user.pk, {})
        rooms = host_counts.get(user.pk, 0)
        score = int(events.get('events') or 0) * 3 + rooms * 5
        if user.last_login and start <= user.last_login <= end:
            score += 2
        candidates[user.pk] = {
            'user': user,
            'events': int(events.get('events') or 0),
            'plays': int(events.get('plays') or 0),
            'completes': int(events.get('completes') or 0),
            'rooms': rooms,
            'score': score,
            'last_seen': events.get('last_seen') or user.last_login or user.date_joined,
        }

    ranked = sorted(candidates.values(), key=lambda item: (-item['score'], item['last_seen'] or timezone.now()), reverse=False)
    ranked.sort(key=lambda item: item['score'], reverse=True)
    result = []
    for item in ranked[:limit]:
        user = item['user']
        watch_minutes = item['plays'] * 12 + item['completes'] * 35 + item['rooms'] * 40
        result.append({
            'user_id': user.pk,
            'username': user.username,
            'watch_time_minutes': watch_minutes,
            'watch_time_hours': round(watch_minutes / 60.0, 1),
            'events': item['events'] + item['rooms'],
            'last_seen': item['last_seen'].isoformat() if item['last_seen'] else None,
        })
    return result


def _top_content_from_db(start, end, limit=10):
    """Rank titles from watch-party usage, then catalog view_count, then ratings/likes."""
    WatchRoom, _, _ = _watchparty_models()
    scores: dict[tuple[str, int], dict] = {}

    if WatchRoom is not None:
        for row in (
            WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end)
            .exclude(movie_id=None)
            .values('movie_id')
            .annotate(count=Count('id'))
        ):
            key = ('movie', int(row['movie_id']))
            scores[key] = {
                'content_type': 'movie',
                'object_id': key[1],
                'activity': row['count'] * 10,
                'playback_events': row['count'],
                'tracked_views': row['count'],
                'completed_views': 0,
            }
        # Map episode rooms up to their series.
        episode_rows = list(
            WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end)
            .exclude(episode_id=None)
            .values('episode_id')
            .annotate(count=Count('id'))
        )
        episode_ids = [row['episode_id'] for row in episode_rows]
        episode_map = {
            ep.pk: ep.season.series_id
            for ep in Episode.objects.filter(pk__in=episode_ids).select_related('season')
        }
        for row in episode_rows:
            series_id = episode_map.get(row['episode_id'])
            if not series_id:
                continue
            key = ('series', int(series_id))
            current = scores.get(key, {
                'content_type': 'series',
                'object_id': series_id,
                'activity': 0,
                'playback_events': 0,
                'tracked_views': 0,
                'completed_views': 0,
            })
            current['activity'] += row['count'] * 10
            current['playback_events'] += row['count']
            current['tracked_views'] += row['count']
            scores[key] = current

    # Catalog view counters (may be zero until tracker writes them).
    for movie in Movie.objects.filter(is_published=True, view_count__gt=0).order_by('-view_count')[:limit]:
        key = ('movie', movie.pk)
        current = scores.get(key, {
            'content_type': 'movie',
            'object_id': movie.pk,
            'activity': 0,
            'playback_events': 0,
            'tracked_views': 0,
            'completed_views': 0,
        })
        current['tracked_views'] = max(current['tracked_views'], int(movie.view_count or 0))
        current['activity'] = max(current['activity'], int(movie.view_count or 0))
        scores[key] = current
    for series in Series.objects.filter(is_published=True, view_count__gt=0).order_by('-view_count')[:limit]:
        key = ('series', series.pk)
        current = scores.get(key, {
            'content_type': 'series',
            'object_id': series.pk,
            'activity': 0,
            'playback_events': 0,
            'tracked_views': 0,
            'completed_views': 0,
        })
        current['tracked_views'] = max(current['tracked_views'], int(series.view_count or 0))
        current['activity'] = max(current['activity'], int(series.view_count or 0))
        scores[key] = current

    # Activity events if tracker is producing data.
    for row in (
        UserActivityEvent.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            content_type__in=('movie', 'series'),
            object_id__isnull=False,
            action__in=(*VIEW_ACTIONS, 'play', 'complete_watch'),
        )
        .values('content_type', 'object_id')
        .annotate(
            activity=Count('id'),
            tracked_views=Count('id', filter=Q(action__in=VIEW_ACTIONS)),
            playback_events=Count('id', filter=Q(action='play')),
            completed_views=Count('id', filter=Q(action='complete_watch')),
        )
    ):
        key = (row['content_type'], int(row['object_id']))
        current = scores.get(key, {
            'content_type': row['content_type'],
            'object_id': row['object_id'],
            'activity': 0,
            'playback_events': 0,
            'tracked_views': 0,
            'completed_views': 0,
        })
        current['activity'] += row['activity']
        current['tracked_views'] += row['tracked_views']
        current['playback_events'] += row['playback_events']
        current['completed_views'] += row['completed_views']
        scores[key] = current

    ranked = sorted(scores.values(), key=lambda item: (-item['activity'], -item['tracked_views']))[:limit]
    movie_ids = [row['object_id'] for row in ranked if row['content_type'] == 'movie']
    series_ids = [row['object_id'] for row in ranked if row['content_type'] == 'series']
    movies = Movie.objects.in_bulk(movie_ids)
    series = Series.objects.in_bulk(series_ids)

    result = []
    for row in ranked:
        item = movies.get(row['object_id']) if row['content_type'] == 'movie' else series.get(row['object_id'])
        result.append({
            'id': row['object_id'],
            'title': item.title if item else 'عنوان حذف‌شده',
            'slug': item.slug if item else '',
            'content_type': row['content_type'],
            'activity': row['activity'],
            'tracked_views': row['tracked_views'],
            'playback_events': row['playback_events'],
            'completed_views': row['completed_views'],
            'view_count': int(getattr(item, 'view_count', 0) or 0),
        })

    # If still empty, fall back to recently published featured / popular catalog.
    if not result:
        for movie in Movie.objects.filter(is_published=True).order_by('-is_featured', '-created_at')[:limit]:
            result.append({
                'id': movie.pk,
                'title': movie.title,
                'slug': movie.slug,
                'content_type': 'movie',
                'activity': 0,
                'tracked_views': int(movie.view_count or 0),
                'playback_events': 0,
                'completed_views': 0,
                'view_count': int(movie.view_count or 0),
            })
    return result


def _sessions_over_time(start_date, days, tz, start, end):
    WatchRoom, _, Playback = _watchparty_models()
    room_rows = {}
    if WatchRoom is not None:
        room_rows = {
            row['day']: row['count']
            for row in (
                WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end)
                .annotate(day=TruncDate('created_at', tzinfo=tz))
                .values('day')
                .annotate(count=Count('id'))
            )
        }
    play_rows = {
        row['day']: row['count']
        for row in (
            UserActivityEvent.objects.filter(
                created_at__gte=start,
                created_at__lte=end,
                action__in=('play', 'watch_progress', 'complete_watch'),
            )
            .annotate(day=TruncDate('created_at', tzinfo=tz))
            .values('day')
            .annotate(count=Count('id'))
        )
    }
    points = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        points.append({
            'date': day.isoformat(),
            'label': day.isoformat(),
            'value': int(room_rows.get(day, 0)) + int(play_rows.get(day, 0)),
        })
    return points


def _activity_heatmap(start, end, tz):
    WatchRoom, _, Playback = _watchparty_models()
    rows: dict[tuple[int, int], int] = {}

    def add_qs(queryset, field='created_at'):
        annotated = (
            queryset
            .annotate(
                weekday=ExtractWeekDay(field, tzinfo=tz),
                hour=ExtractHour(field, tzinfo=tz),
            )
            .values('weekday', 'hour')
            .annotate(count=Count('id'))
        )
        for row in annotated:
            if row['weekday'] is None or row['hour'] is None:
                continue
            key = (int(row['weekday']), int(row['hour']))
            rows[key] = rows.get(key, 0) + int(row['count'])

    if WatchRoom is not None:
        add_qs(WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end), 'created_at')
    if Playback is not None:
        add_qs(Playback.objects.filter(updated_at__gte=start, updated_at__lte=end), 'updated_at')
    add_qs(
        UserActivityEvent.objects.filter(created_at__gte=start, created_at__lte=end),
        'created_at',
    )
    add_qs(
        User.objects.filter(last_login__gte=start, last_login__lte=end, last_login__isnull=False),
        'last_login',
    )

    weekday_order = [7, 1, 2, 3, 4, 5, 6]
    cells = []
    for weekday in weekday_order:
        for hour in range(24):
            cells.append({
                'weekday': weekday,
                'weekday_label': WEEKDAY_LABELS_FA[weekday],
                'hour': hour,
                'value': rows.get((weekday, hour), 0),
            })
    return {
        'weekdays': [{'id': d, 'label': WEEKDAY_LABELS_FA[d]} for d in weekday_order],
        'hours': list(range(24)),
        'cells': cells,
    }


def _recent_content(limit=12):
    movies = list(
        Movie.objects.filter(is_published=True)
        .order_by('-created_at')
        .values('id', 'title', 'slug', 'view_count', 'created_at', 'is_dubbed', 'has_subtitle')[:limit]
    )
    series = list(
        Series.objects.filter(is_published=True)
        .order_by('-created_at')
        .values('id', 'title', 'slug', 'view_count', 'created_at', 'is_dubbed', 'has_subtitle')[:limit]
    )
    merged = [
        {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'content_type': 'movie',
            'view_count': int(row['view_count'] or 0),
            'is_dubbed': bool(row.get('is_dubbed')),
            'has_subtitle': bool(row.get('has_subtitle')),
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        }
        for row in movies
    ] + [
        {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'content_type': 'series',
            'view_count': int(row['view_count'] or 0),
            'is_dubbed': bool(row.get('is_dubbed')),
            'has_subtitle': bool(row.get('has_subtitle')),
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        }
        for row in series
    ]
    merged.sort(key=lambda item: item['created_at'] or '', reverse=True)
    return merged[:limit]


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_overview(request):
    days = _parse_period(request)
    win = _window(days)

    total_users = User.objects.count()
    active_users = User.objects.filter(
        is_active=True,
        last_login__gte=win['start'],
        last_login__lte=win['end'],
    ).count()
    previous_active = User.objects.filter(
        is_active=True,
        last_login__gte=win['previous_start'],
        last_login__lt=win['previous_end'],
    ).count()
    # Also count distinct event actors in period.
    active_from_events = (
        UserActivityEvent.objects.filter(
            created_at__gte=win['start'],
            created_at__lte=win['end'],
            user_id__isnull=False,
        )
        .values('user_id')
        .distinct()
        .count()
    )
    active_users = max(active_users, active_from_events)

    today_start = win['local_now'].replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = User.objects.filter(date_joined__gte=today_start).count()
    new_yesterday = User.objects.filter(
        date_joined__gte=today_start - timedelta(days=1),
        date_joined__lt=today_start,
    ).count()

    movies_pub = Movie.objects.filter(is_published=True).count()
    series_pub = Series.objects.filter(is_published=True).count()
    episodes_pub = Episode.objects.filter(is_published=True).count()
    total_content = movies_pub + series_pub

    period_new = User.objects.filter(date_joined__gte=win['start'], date_joined__lte=win['end']).count()
    previous_period_new = User.objects.filter(
        date_joined__gte=win['previous_start'],
        date_joined__lt=win['previous_end'],
    ).count()

    watch_hours = _watch_hours_from_db(win['start'], win['end'])
    previous_watch_hours = _watch_hours_from_db(win['previous_start'], win['previous_end'])

    dubbed = Movie.objects.filter(is_published=True, is_dubbed=True).count() + Series.objects.filter(
        is_published=True, is_dubbed=True,
    ).count()
    subtitled = Movie.objects.filter(is_published=True, has_subtitle=True).count() + Series.objects.filter(
        is_published=True, has_subtitle=True,
    ).count()

    data = {
        'kpis': [
            {
                'id': 'total_users',
                'label': 'کل کاربران',
                'value': total_users,
                'delta_percent': _comparison(period_new, previous_period_new)['change_percent'],
                'format': 'number',
                'hint': f'{period_new} عضویت در بازه',
            },
            {
                'id': 'active_users',
                'label': 'کاربران فعال',
                'value': active_users,
                'delta_percent': _comparison(active_users, previous_active)['change_percent'],
                'format': 'number',
                'hint': f'ورود در {days} روز اخیر',
            },
            {
                'id': 'new_signups_today',
                'label': 'عضویت امروز',
                'value': new_today,
                'delta_percent': _comparison(new_today, new_yesterday)['change_percent'],
                'format': 'number',
            },
            {
                'id': 'total_content',
                'label': 'کل محتوا',
                'value': total_content,
                'delta_percent': None,
                'format': 'number',
                'hint': f'{movies_pub} فیلم · {series_pub} سریال · {episodes_pub} قسمت',
            },
            {
                'id': 'watch_hours',
                'label': 'ساعت تماشا',
                'value': watch_hours,
                'delta_percent': _comparison(int(watch_hours * 10), int(previous_watch_hours * 10))['change_percent'],
                'format': 'hours',
                'hint': 'از واچ‌پارتی و رویداد پخش',
            },
            {
                'id': 'revenue',
                'label': 'درآمد',
                'value': None,
                'delta_percent': None,
                'format': 'currency',
                'hint': 'مدل درآمد هنوز فعال نیست',
            },
        ],
        'realtime': _online_snapshot(win['now']),
        'catalog': {
            'movies': movies_pub,
            'series': series_pub,
            'episodes': episodes_pub,
            'total': total_content,
            'dubbed': dubbed,
            'with_subtitle': subtitled,
        },
        'database': {
            'activity_events': UserActivityEvent.objects.count(),
            'likes': Like.objects.count(),
            'ratings': Rating.objects.count(),
            'watchlist': WatchlistItem.objects.count(),
        },
    }
    return Response(_envelope(data, days=days, now=win['now'], win=win))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_users(request):
    days = _parse_period(request)
    win = _window(days)
    granularity = str(request.query_params.get('granularity') or 'daily').strip().lower()
    if granularity not in {'daily', 'weekly', 'monthly'}:
        granularity = 'daily'

    users_qs = User.objects.filter(date_joined__gte=win['start'], date_joined__lte=win['end'])
    events = UserActivityEvent.objects.filter(created_at__gte=win['start'], created_at__lte=win['end'])

    data = {
        'registrations': {
            'granularity': granularity,
            'points': _registrations_series(
                users_qs,
                start_date=win['start_date'],
                days=days,
                tz=win['tz'],
                granularity=granularity,
            ),
        },
        'active_by_weekday': _active_by_weekday_from_logins(win['start'], win['end'], win['tz']),
        'devices': _normalize_device_breakdown(_device_breakdown(events)),
        'top_active_users': _top_active_users(win['start'], win['end'], limit=10),
        'totals': {
            'users': User.objects.count(),
            'active_in_period': User.objects.filter(
                last_login__gte=win['start'],
                last_login__lte=win['end'],
            ).count(),
            'new_in_period': users_qs.count(),
        },
    }
    return Response(_envelope(data, days=days, now=win['now'], win=win))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_content_top(request):
    days = _parse_period(request)
    win = _window(days)
    data = {
        'top_watched': _top_content_from_db(win['start'], win['end'], limit=10),
        'sessions_over_time': _sessions_over_time(
            win['start_date'],
            days,
            win['tz'],
            win['start'],
            win['end'],
        ),
        'heatmap': _activity_heatmap(win['start'], win['end'], win['tz']),
        'recently_added': _recent_content(limit=12),
        'catalog': {
            'movies_published': Movie.objects.filter(is_published=True).count(),
            'series_published': Series.objects.filter(is_published=True).count(),
            'episodes_published': Episode.objects.filter(is_published=True).count(),
        },
    }
    return Response(_envelope(data, days=days, now=win['now'], win=win))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_engagement(request):
    days = _parse_period(request)
    win = _window(days)
    events = UserActivityEvent.objects.filter(created_at__gte=win['start'], created_at__lte=win['end'])

    plays = events.filter(action='play').count()
    completes = events.filter(action='complete_watch').count()
    views = events.filter(action__in=VIEW_ACTIONS).count()

    WatchRoom, _, Playback = _watchparty_models()
    rooms_in_period = 0
    if WatchRoom is not None:
        rooms_in_period = WatchRoom.objects.filter(
            created_at__gte=win['start'],
            created_at__lte=win['end'],
        ).count()

    avg_session_minutes = 0.0
    if Playback is not None:
        agg = Playback.objects.filter(
            updated_at__gte=win['start'],
            updated_at__lte=win['end'],
            position_seconds__gt=0,
        ).aggregate(avg_pos=Avg('position_seconds'))
        avg_pos = float(agg['avg_pos'] or 0)
        if avg_pos > 0:
            avg_session_minutes = round(avg_pos / 60.0, 1)

    completion_by_content = []
    for row in _top_content_from_db(win['start'], win['end'], limit=10):
        completion_by_content.append({
            'id': row['id'],
            'title': row['title'],
            'content_type': row['content_type'],
            'playback_events': row['playback_events'],
            'completed_views': row['completed_views'],
            'completion_rate': _rate(row['completed_views'], row['playback_events'] or row['tracked_views']),
        })

    likes_period = Like.objects.filter(created_at__gte=win['start'], created_at__lte=win['end']).count()
    ratings_period = Rating.objects.filter(created_at__gte=win['start'], created_at__lte=win['end']).count()
    watchlist_period = WatchlistItem.objects.filter(
        created_at__gte=win['start'],
        created_at__lte=win['end'],
    ).count()
    rating_avg = Rating.objects.aggregate(avg=Avg('score'))['avg']

    searches = _top_searches(events, limit=20)

    data = {
        'average_session_minutes': avg_session_minutes,
        'completion_rate': _rate(completes, plays or views) if (plays or views) else None,
        'plays': plays,
        'completes': completes,
        'views': views,
        'watch_rooms': rooms_in_period,
        'likes_total': Like.objects.count(),
        'likes_in_period': likes_period,
        'ratings_total': Rating.objects.count(),
        'ratings_in_period': ratings_period,
        'average_rating': round(float(rating_avg), 1) if rating_avg is not None else None,
        'watchlist_total': WatchlistItem.objects.count(),
        'watchlist_in_period': watchlist_period,
        'completion_by_content': completion_by_content,
        'search_terms': [
            {
                'term': row['query'],
                'count': row['count'],
                'zero_result_count': row.get('zero_result_count') or 0,
            }
            for row in searches
        ],
        'realtime': _online_snapshot(win['now']),
    }
    return Response(_envelope(data, days=days, now=win['now'], win=win))


class PresenceAnonThrottle(AnonRateThrottle):
    rate = '60/min'


class PresenceUserThrottle(UserRateThrottle):
    rate = '120/min'


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PresenceAnonThrottle, PresenceUserThrottle])
def analytics_presence(request):
    """Lightweight heartbeat used for accurate online counts."""
    user_id = request.user.pk if getattr(request.user, 'is_authenticated', False) else None
    anon = str(request.data.get('anonymous_session_id') or request.headers.get('X-Anonymous-Session-ID') or '').strip()
    touch_presence(user_id=user_id, anonymous_session_id=anon or None)
    return Response({
        'ok': True,
        'window_seconds': PRESENCE_WINDOW_SECONDS,
        'authenticated': bool(user_id),
    })
