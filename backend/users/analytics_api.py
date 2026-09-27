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
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.catalog.models import Episode, Movie, Series
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem
from users.admin_api import IsStaffUser, StaffAdminThrottle
from users.dashboard_api import (
    ACTION_LABELS,
    VIEW_ACTIONS,
    _comparison,
    _device_breakdown,
    _rate,
    _top_searches,
)
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
    """Real watch hours in the window.

    Sourced from recorded playback progress × catalog runtime (the same honest
    ``runtime × progress/100`` model used for per-user watch stats), plus the
    watched playhead position advanced in watch-party rooms. No fabricated
    per-play minutes — an empty tracker reads 0, never a guess.
    """
    from apps.engagement.watch_stats import total_watch_minutes

    minutes = total_watch_minutes(start, end)

    _, _, Playback = _watchparty_models()
    if Playback is not None:
        agg = Playback.objects.filter(updated_at__gte=start, updated_at__lte=end).aggregate(
            total_pos=Sum('position_seconds'),
        )
        minutes += float(agg['total_pos'] or 0) / 60.0

    return round(minutes / 60.0, 1)


def _active_user_ids(start, end) -> set[int]:
    """Distinct users active in [start, end] — union of logins and tracked events.

    A user active only through the SPA (activity events) and a user with only a
    fresh ``last_login`` are disjoint populations; unioning them avoids
    undercounting real activity.
    """
    ids = set(
        User.objects.filter(is_active=True, last_login__gte=start, last_login__lte=end)
        .values_list('id', flat=True)
    )
    ids |= {
        int(uid)
        for uid in UserActivityEvent.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            user_id__isnull=False,
        ).values_list('user_id', flat=True).distinct()
    }
    return ids


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


def _action_breakdown(events, limit=12):
    """Real event-type mix — replaces device telemetry that consent rules never record."""
    rows = list(
        events
        .values('action')
        .annotate(count=Count('id'))
        .order_by('-count', 'action')[:limit]
    )
    labels = dict(ACTION_LABELS)
    return [
        {
            'id': row['action'],
            'label': labels.get(row['action'], row['action']),
            'value': row['count'],
        }
        for row in rows
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
    """Leaderboard of the most active real users in the window.

    Every signal is real DB data — no fabricated watch minutes:
      - interaction count: UserActivityEvent rows the user produced
      - plays / completes: real playback events
      - rooms_hosted: watch-party rooms the user opened
      - likes / ratings: engagement created in the window
      - watch_time: recorded progress × catalog runtime (watch_stats model)

    Candidates are anyone with *any* real signal in the window (events, hosted
    rooms, likes, ratings, or a login), not just the 80 most-recent logins, so
    a heavy watcher can never be missed by an arbitrary cutoff.
    """
    from apps.engagement.watch_stats import watch_minutes_by_user

    WatchRoom, _, _ = _watchparty_models()

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

    host_counts: dict[int, int] = {}
    if WatchRoom is not None:
        for row in (
            WatchRoom.objects.filter(created_at__gte=start, created_at__lte=end)
            .exclude(host_user_id=None)
            .values('host_user_id')
            .annotate(count=Count('id'))
        ):
            host_counts[row['host_user_id']] = row['count']

    like_counts = {
        row['user_id']: row['count']
        for row in (
            Like.objects.filter(created_at__gte=start, created_at__lte=end, user_id__isnull=False)
            .values('user_id')
            .annotate(count=Count('id'))
        )
    }
    rating_counts = {
        row['user_id']: row['count']
        for row in (
            Rating.objects.filter(created_at__gte=start, created_at__lte=end, user_id__isnull=False)
            .values('user_id')
            .annotate(count=Count('id'))
        )
    }

    candidate_ids = set(event_rows) | set(host_counts) | set(like_counts) | set(rating_counts)
    candidate_ids |= set(
        User.objects.filter(last_login__gte=start, last_login__lte=end, is_active=True)
        .values_list('id', flat=True)
    )
    if not candidate_ids:
        return []

    watch_minutes = watch_minutes_by_user(start, end, user_ids=candidate_ids)
    users = User.objects.filter(pk__in=candidate_ids).exclude(is_staff=True).in_bulk()

    result = []
    for uid, user in users.items():
        ev = event_rows.get(uid, {})
        events = int(ev.get('events') or 0)
        rooms = int(host_counts.get(uid, 0))
        likes = int(like_counts.get(uid, 0))
        ratings = int(rating_counts.get(uid, 0))
        interactions = events + rooms + likes + ratings
        logged_in_window = bool(user.last_login and start <= user.last_login <= end)
        if interactions == 0 and not logged_in_window:
            continue
        minutes = float(watch_minutes.get(uid, 0.0))
        last_seen = ev.get('last_seen') or user.last_login or user.date_joined
        result.append({
            'user_id': uid,
            'username': user.username,
            'watch_time_minutes': round(minutes, 1),
            'watch_time_hours': round(minutes / 60.0, 1),
            'events': events,
            'plays': int(ev.get('plays') or 0),
            'completes': int(ev.get('completes') or 0),
            'rooms_hosted': rooms,
            'likes': likes,
            'ratings': ratings,
            'interactions': interactions,
            'last_seen': last_seen.isoformat() if last_seen else None,
        })

    result.sort(key=lambda r: (r['interactions'], r['watch_time_minutes']), reverse=True)
    return result[:limit]


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


def _json_key_breakdown(queryset, key, *, fallback='نامشخص', limit=None):
    """Aggregate a JSONField metadata key into label/value slices (real counts).

    Empty strings are stripped at ingestion, so a missing key reads as NULL and
    is folded into the fallback label rather than silently dropped.
    """
    tallies: dict[str, int] = {}
    for row in queryset.values(f'metadata__{key}').annotate(count=Count('id')):
        raw = row.get(f'metadata__{key}')
        label = (str(raw).strip() if raw not in (None, '') else '') or fallback
        tallies[label] = tallies.get(label, 0) + int(row['count'])
    slices = [{'label': label, 'value': value} for label, value in tallies.items()]
    slices.sort(key=lambda item: -item['value'])
    return slices[:limit] if limit else slices


def _downloads_analytics(win, *, days, limit=10):
    """Real download analytics from `download_click` UserActivityEvents.

    Every figure is a live DB count — no placeholders. Until clients emit the
    new `download` signal these come back zero honestly rather than fabricated.
    """
    tz = win['tz']
    base = UserActivityEvent.objects.filter(action='download_click')
    period_qs = base.filter(created_at__gte=win['start'], created_at__lte=win['end'])
    prev_qs = base.filter(created_at__gte=win['previous_start'], created_at__lt=win['previous_end'])

    total_all = base.count()
    total_period = period_qs.count()
    total_prev = prev_qs.count()

    unique_users_period = period_qs.filter(user_id__isnull=False).values('user_id').distinct().count()
    unique_sessions_period = period_qs.exclude(session_key='').values('session_key').distinct().count()

    # Downloads over time (one point per day across the window).
    day_rows = {
        row['day']: row['count']
        for row in (
            period_qs.annotate(day=TruncDate('created_at', tzinfo=tz))
            .values('day')
            .annotate(count=Count('id'))
        )
    }
    over_time = []
    for offset in range(days):
        day = win['start_date'] + timedelta(days=offset)
        over_time.append({
            'date': day.isoformat(),
            'label': day.isoformat(),
            'value': int(day_rows.get(day, 0)),
        })

    # Top-downloaded titles (resolve movie/series titles from real event rows).
    top_rows = list(
        period_qs.filter(content_type__in=('movie', 'series'), object_id__isnull=False)
        .values('content_type', 'object_id')
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )
    movie_ids = [r['object_id'] for r in top_rows if r['content_type'] == 'movie']
    series_ids = [r['object_id'] for r in top_rows if r['content_type'] == 'series']
    movies = Movie.objects.in_bulk(movie_ids)
    series = Series.objects.in_bulk(series_ids)
    top_titles = []
    for row in top_rows:
        item = movies.get(row['object_id']) if row['content_type'] == 'movie' else series.get(row['object_id'])
        top_titles.append({
            'id': row['object_id'],
            'title': item.title if item else 'عنوان حذف‌شده',
            'slug': item.slug if item else '',
            'content_type': row['content_type'],
            'downloads': int(row['count']),
        })

    ct_tallies = {'movie': 0, 'series': 0}
    for row in period_qs.values('content_type').annotate(count=Count('id')):
        if row['content_type'] in ct_tallies:
            ct_tallies[row['content_type']] += int(row['count'])
    by_type = [
        {'label': 'فیلم', 'value': ct_tallies['movie']},
        {'label': 'سریال', 'value': ct_tallies['series']},
    ]

    return {
        'summary': {
            'total_all_time': total_all,
            'total_period': total_period,
            'delta_percent': _comparison(total_period, total_prev)['change_percent'],
            'unique_users': unique_users_period,
            'unique_sessions': unique_sessions_period,
            'per_user': round(total_period / unique_users_period, 1) if unique_users_period else 0.0,
        },
        'over_time': over_time,
        'top_titles': top_titles,
        'by_quality': _json_key_breakdown(period_qs, 'quality', limit=8),
        'by_platform': _json_key_breakdown(period_qs, 'platform'),
        'by_type': by_type,
        'tracking_active': total_all > 0,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_downloads(request):
    days = _parse_period(request)
    win = _window(days)
    data = _downloads_analytics(win, days=days, limit=12)
    return Response(_envelope(data, days=days, now=win['now'], win=win))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_overview(request):
    days = _parse_period(request)
    win = _window(days)

    total_users = User.objects.count()
    active_user_ids = set(User.objects.filter(
        is_active=True,
        last_login__gte=win['start'],
        last_login__lte=win['end'],
    ).values_list('id', flat=True))
    previous_active_ids = set(User.objects.filter(
        is_active=True,
        last_login__gte=win['previous_start'],
        last_login__lt=win['previous_end'],
    ).values_list('id', flat=True))
    # Use a union, not max(counts): users active through events and users with
    # a recent login can be disjoint sets.
    active_user_ids.update(
        UserActivityEvent.objects.filter(
            created_at__gte=win['start'],
            created_at__lte=win['end'],
            user_id__isnull=False,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    previous_active_ids.update(
        UserActivityEvent.objects.filter(
            created_at__gte=win['previous_start'],
            created_at__lt=win['previous_end'],
            user_id__isnull=False,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    active_users = len(active_user_ids)
    previous_active = len(previous_active_ids)

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

    likes_period = Like.objects.filter(created_at__gte=win['start'], created_at__lte=win['end']).count()

    downloads_all = UserActivityEvent.objects.filter(action='download_click').count()
    downloads_period = UserActivityEvent.objects.filter(
        action='download_click',
        created_at__gte=win['start'],
        created_at__lte=win['end'],
    ).count()
    downloads_prev = UserActivityEvent.objects.filter(
        action='download_click',
        created_at__gte=win['previous_start'],
        created_at__lt=win['previous_end'],
    ).count()

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
                'id': 'likes_total',
                'label': 'لایک‌ها',
                'value': Like.objects.count(),
                'delta_percent': None,
                'format': 'number',
                'hint': f'{likes_period} لایک در بازه',
            },
            {
                'id': 'downloads_total',
                'label': 'دانلودها',
                'value': downloads_all,
                'delta_percent': _comparison(downloads_period, downloads_prev)['change_percent'],
                'format': 'number',
                'hint': f'{downloads_period} دانلود در بازه',
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

    now = win['now']
    breakdown = User.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        inactive=Count('id', filter=Q(is_active=False)),
        verified=Count('id', filter=Q(is_verified=True)),
        staff=Count('id', filter=Q(is_staff=True)),
    )
    total_users = int(breakdown['total'] or 0)
    verified_users = int(breakdown['verified'] or 0)

    # Rolling stickiness windows (independent of the selected report period).
    dau = len(_active_user_ids(now - timedelta(days=1), now))
    wau = len(_active_user_ids(now - timedelta(days=7), now))
    mau = len(_active_user_ids(now - timedelta(days=30), now))

    period_active_ids = _active_user_ids(win['start'], win['end'])
    active_in_period = len(period_active_ids)
    # Returning = users active in the window who registered before it began.
    returning_in_period = (
        User.objects.filter(pk__in=period_active_ids, date_joined__lt=win['start']).count()
        if period_active_ids else 0
    )
    today_start = win['local_now'].replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = User.objects.filter(date_joined__gte=today_start).count()
    new_in_period = users_qs.count()

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
        'action_breakdown': _action_breakdown(events),
        'devices': _normalize_device_breakdown(_device_breakdown(events)),
        'top_active_users': _top_active_users(win['start'], win['end'], limit=10),
        'totals': {
            'users': total_users,
            'active_in_period': active_in_period,
            'new_in_period': new_in_period,
            'new_today': new_today,
            'returning_in_period': returning_in_period,
            'dau': dau,
            'wau': wau,
            'mau': mau,
            'active': int(breakdown['active'] or 0),
            'inactive': int(breakdown['inactive'] or 0),
            'verified': verified_users,
            'unverified': total_users - verified_users,
            'staff': int(breakdown['staff'] or 0),
            'verified_rate': _rate(verified_users, total_users),
            'stickiness': _rate(dau, mau),
        },
    }
    return Response(_envelope(data, days=days, now=win['now'], win=win))


def _top_by_views(model, content_type, limit=8):
    """Real most-viewed titles straight from the denormalised catalog counter."""
    return [
        {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'content_type': content_type,
            'view_count': int(row['view_count'] or 0),
        }
        for row in (
            model.objects.filter(is_published=True, view_count__gt=0)
            .order_by('-view_count')
            .values('id', 'title', 'slug', 'view_count')[:limit]
        )
    ]


def _content_view_stats(start, end):
    """Real movie/series view aggregates for the content dashboard.

    ``total_views`` is the lifetime denormalised counter (kept live by the
    activity serializer + backfilled from tracked events); ``period_views`` is
    tracked view events inside the selected window. Both are real, never seeded.
    """
    movie_total = Movie.objects.filter(is_published=True).aggregate(
        total=Sum('view_count'), titles=Count('id', filter=Q(view_count__gt=0)),
    )
    series_total = Series.objects.filter(is_published=True).aggregate(
        total=Sum('view_count'), titles=Count('id', filter=Q(view_count__gt=0)),
    )
    period = dict(
        UserActivityEvent.objects.filter(
            created_at__gte=start,
            created_at__lte=end,
            action__in=VIEW_ACTIONS,
        )
        .values_list('action')
        .annotate(n=Count('id'))
    )
    movie_views = int(movie_total['total'] or 0)
    series_views = int(series_total['total'] or 0)
    return {
        'movie_views': movie_views,
        'series_views': series_views,
        'total_views': movie_views + series_views,
        'movie_titles_viewed': int(movie_total['titles'] or 0),
        'series_titles_viewed': int(series_total['titles'] or 0),
        'movie_views_in_period': int(period.get('view_movie', 0) or 0),
        'series_views_in_period': int(period.get('view_series', 0) or 0),
        'top_movies': _top_by_views(Movie, 'movie', limit=8),
        'top_series': _top_by_views(Series, 'series', limit=8),
    }


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
        'stats': _content_view_stats(win['start'], win['end']),
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


# ---------------------------------------------------------------------------
# Behaviour analytics — cohesive real-data view of *how* people use the site.
# Every figure below is a live count/aggregate over UserActivityEvent (and the
# auth log for retention). Nothing is seeded; empty windows read as zero.
# ---------------------------------------------------------------------------

FUNNEL_VIEW_ACTIONS = ('view_movie', 'view_series', 'view_episode')
CONTENT_TYPE_LABELS_FA = {
    'movie': 'فیلم',
    'series': 'سریال',
    'episode': 'قسمت',
    'actor': 'بازیگر',
    'director': 'کارگردان',
    'genre': 'ژانر',
    'search': 'جستجو',
}


def _behavior_funnel(events):
    """Consumption funnel: page view → play → in-progress → complete.

    Each stage is a real event count in the window. ``step_conversion`` is the
    drop-off from the previous stage; ``pct_of_top`` positions every stage
    against the funnel entry so the shape is readable at a glance.
    """
    counts = events.aggregate(
        page_views=Count('id', filter=Q(action__in=FUNNEL_VIEW_ACTIONS)),
        plays=Count('id', filter=Q(action='play')),
        progress=Count('id', filter=Q(action='watch_progress')),
        completes=Count('id', filter=Q(action='complete_watch')),
    )
    stages = [
        ('page_view', 'بازدید صفحه', int(counts['page_views'] or 0)),
        ('play', 'شروع پخش', int(counts['plays'] or 0)),
        ('watch_progress', 'در حال تماشا', int(counts['progress'] or 0)),
        ('complete', 'تماشای کامل', int(counts['completes'] or 0)),
    ]
    top = stages[0][2]
    result = []
    prev = None
    for key, label, value in stages:
        result.append({
            'id': key,
            'label': label,
            'value': value,
            'pct_of_top': _rate(value, top),
            'step_conversion': _rate(value, prev) if prev is not None else None,
        })
        prev = value
    return {
        'stages': result,
        'play_through_rate': _rate(stages[1][2], stages[0][2]),
        'completion_rate': _rate(stages[3][2], stages[1][2]),
    }


def _discovery_metrics(events):
    """Search → click-through behaviour, all from real search events."""
    searches = events.filter(action='search', content_type='search')
    total_searches = searches.count()
    zero_result = searches.filter(metadata__result_count=0).count()
    clicks = events.filter(action='click_search_result').count()
    unique_terms = searches.exclude(query='').values('query').distinct().count()
    return {
        'searches': total_searches,
        'unique_terms': unique_terms,
        'result_clicks': clicks,
        'click_through_rate': _rate(clicks, total_searches),
        'zero_result_searches': zero_result,
        'zero_result_rate': _rate(zero_result, total_searches),
        'top_terms': [
            {
                'term': row['query'],
                'count': row['count'],
                'zero_result_count': row.get('zero_result_count') or 0,
            }
            for row in _top_searches(events, limit=12)
        ],
    }


def _session_depth(events):
    """Per-session engagement depth from real session_key groupings.

    A "session" is one ``session_key`` bucket (anonymous or logged-in). We read
    event count and first/last timestamp per session, then summarise depth,
    duration and the single-touch (bounce) share — no sampling, no estimates.
    """
    rows = list(
        events.exclude(session_key='')
        .values('session_key')
        .annotate(n=Count('id'), first=Min('created_at'), last=Max('created_at'))
    )
    total = len(rows)
    if not total:
        return {
            'sessions': 0,
            'avg_events_per_session': 0.0,
            'median_events_per_session': 0,
            'avg_duration_minutes': 0.0,
            'bounce_rate': None,
            'depth_distribution': [
                {'id': '1', 'label': '۱ رویداد', 'value': 0},
                {'id': '2-3', 'label': '۲ تا ۳', 'value': 0},
                {'id': '4-10', 'label': '۴ تا ۱۰', 'value': 0},
                {'id': '11+', 'label': '۱۱ به بالا', 'value': 0},
            ],
        }
    depths = sorted(int(r['n']) for r in rows)
    total_events = sum(depths)
    single = sum(1 for d in depths if d == 1)
    mid = total // 2
    median = depths[mid] if total % 2 else (depths[mid - 1] + depths[mid]) // 2

    duration_seconds = 0.0
    measured = 0
    for r in rows:
        first, last = r['first'], r['last']
        if first and last:
            duration_seconds += (last - first).total_seconds()
            measured += 1
    avg_duration_minutes = round((duration_seconds / measured) / 60.0, 1) if measured else 0.0

    buckets = {'1': 0, '2-3': 0, '4-10': 0, '11+': 0}
    for d in depths:
        if d <= 1:
            buckets['1'] += 1
        elif d <= 3:
            buckets['2-3'] += 1
        elif d <= 10:
            buckets['4-10'] += 1
        else:
            buckets['11+'] += 1
    bucket_labels = {'1': '۱ رویداد', '2-3': '۲ تا ۳', '4-10': '۴ تا ۱۰', '11+': '۱۱ به بالا'}
    return {
        'sessions': total,
        'avg_events_per_session': round(total_events / total, 1),
        'median_events_per_session': median,
        'avg_duration_minutes': avg_duration_minutes,
        'bounce_rate': _rate(single, total),
        'depth_distribution': [
            {'id': key, 'label': bucket_labels[key], 'value': buckets[key]}
            for key in ('1', '2-3', '4-10', '11+')
        ],
    }


def _content_interest(events):
    """Where attention goes — event volume split by content type (real counts)."""
    rows = (
        events.exclude(content_type='')
        .values('content_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    return [
        {
            'id': row['content_type'],
            'label': CONTENT_TYPE_LABELS_FA.get(row['content_type'], row['content_type']),
            'value': int(row['count'] or 0),
        }
        for row in rows
    ]


def _retention_snapshot(now):
    """Real stickiness + week-over-week retention from logins and events.

    - DAU/WAU/MAU + stickiness (DAU/MAU) reuse ``_active_user_ids``.
    - WoW retention: of users active in the week before last, how many came
      back in the most recent 7 days. Pure set intersection over real activity.
    """
    dau = len(_active_user_ids(now - timedelta(days=1), now))
    wau = len(_active_user_ids(now - timedelta(days=7), now))
    mau = len(_active_user_ids(now - timedelta(days=30), now))

    prev_week = _active_user_ids(now - timedelta(days=14), now - timedelta(days=7))
    this_week = _active_user_ids(now - timedelta(days=7), now)
    retained = len(prev_week & this_week)
    return {
        'dau': dau,
        'wau': wau,
        'mau': mau,
        'stickiness': _rate(dau, mau),
        'wow_retention_rate': _rate(retained, len(prev_week)) if prev_week else None,
        'wow_prior_cohort': len(prev_week),
        'wow_retained': retained,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def analytics_behavior(request):
    """Cohesive user-behaviour analytics — one payload, all real DB signals."""
    days = _parse_period(request)
    win = _window(days)
    events = UserActivityEvent.objects.filter(
        created_at__gte=win['start'], created_at__lte=win['end'],
    )

    tracked_events = events.count()
    active_users = events.filter(user_id__isnull=False).values('user_id').distinct().count()
    anon_sessions = events.filter(user_id__isnull=True).exclude(session_key='').values('session_key').distinct().count()

    engagement_actions = events.aggregate(
        likes=Count('id', filter=Q(action='like')),
        ratings=Count('id', filter=Q(action='rate')),
        watchlist=Count('id', filter=Q(action='add_to_watchlist')),
        shares=Count('id', filter=Q(action='share')),
        downloads=Count('id', filter=Q(action='download_click')),
        trailers=Count('id', filter=Q(action='trailer_watch')),
    )

    data = {
        'summary': {
            'tracked_events': tracked_events,
            'active_users': active_users,
            'anonymous_sessions': anon_sessions,
            'events_per_active': round(tracked_events / active_users, 1) if active_users else None,
            'engagement_actions': {k: int(v or 0) for k, v in engagement_actions.items()},
        },
        'funnel': _behavior_funnel(events),
        'discovery': _discovery_metrics(events),
        'sessions': _session_depth(events),
        'action_mix': _action_breakdown(events, limit=14),
        'content_interest': _content_interest(events),
        'heatmap': _activity_heatmap(win['start'], win['end'], win['tz']),
        'retention': _retention_snapshot(win['now']),
        'top_active_users': _top_active_users(win['start'], win['end'], limit=10),
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
