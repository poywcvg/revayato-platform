"""Per-user watch-time estimates from privacy-safe activity events.

We do not store wall-clock playhead seconds yet. Instead we estimate minutes
watched as ``duration_minutes * max_progress / 100`` per title, using catalog
durations. Completes count as 100%. Weekly deltas compare progress before
the window vs now so returning mid-title does not inflate the week total.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone

from apps.catalog.models import Episode, Movie
from apps.engagement.models import UserActivityEvent

WATCH_ACTIONS = ('play', 'watch_progress', 'complete_watch', 'pause')
DEFAULT_MOVIE_MINUTES = 110
DEFAULT_SERIES_EPISODE_MINUTES = 45


def _clamp_progress(value) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _duration_lookup(keys: set[tuple[str, int]]) -> dict[tuple[str, int], float]:
    """Map (content_type, object_id) -> duration minutes used for estimates."""
    movie_ids = [oid for ctype, oid in keys if ctype == 'movie']
    series_ids = [oid for ctype, oid in keys if ctype == 'series']
    durations: dict[tuple[str, int], float] = {}

    if movie_ids:
        for row in Movie.objects.filter(pk__in=movie_ids).values('id', 'duration_minutes'):
            minutes = row['duration_minutes'] or DEFAULT_MOVIE_MINUTES
            durations[('movie', int(row['id']))] = float(minutes)

    if series_ids:
        episode_avgs = {
            int(row['season__series_id']): float(row['avg_duration'] or 0)
            for row in (
                Episode.objects.filter(season__series_id__in=series_ids)
                .values('season__series_id')
                .annotate(avg_duration=Avg('duration_minutes'))
            )
        }
        for sid in series_ids:
            avg = episode_avgs.get(int(sid)) or 0.0
            durations[('series', int(sid))] = avg if avg > 0 else float(DEFAULT_SERIES_EPISODE_MINUTES)

    for key in keys:
        durations.setdefault(key, float(DEFAULT_MOVIE_MINUTES if key[0] == 'movie' else DEFAULT_SERIES_EPISODE_MINUTES))
    return durations


def _progress_snapshots(user, *, since=None, until=None) -> dict[tuple[str, int], float]:
    """Max observed progress per title in an optional time window."""
    qs = UserActivityEvent.objects.filter(
        user=user,
        action__in=WATCH_ACTIONS,
        object_id__isnull=False,
        content_type__in=('movie', 'series'),
    )
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)

    snapshots: dict[tuple[str, int], float] = defaultdict(float)
    for row in qs.values('content_type', 'object_id', 'action', 'progress'):
        key = (str(row['content_type']), int(row['object_id']))
        if row['action'] == 'complete_watch':
            snapshots[key] = 100.0
            continue
        progress = _clamp_progress(row['progress'])
        if progress > snapshots[key]:
            snapshots[key] = progress
    return dict(snapshots)


def _minutes_from_progress(progress: float, duration: float) -> float:
    return max(0.0, duration * (max(0.0, min(100.0, progress)) / 100.0))


def _milestone_for(total_minutes: float) -> dict:
    tiers = [
        (0, 'تازه‌وارد پرده', 'اولین دقیقه‌ها را روی روایتو ثبت کن.'),
        (30, 'جرقه اول', 'نیم ساعت تماشا؛ قلاب زده شد.'),
        (60, 'یک ساعت با روایت', 'اولین ساعت کامل تماشایت ثبت شد.'),
        (180, 'تماشاگر شبانه', 'سه ساعت — انگار یک شب سینما بود.'),
        (600, 'پردهٔ شخصی', 'ده ساعت تماشا؛ سلیقه‌ات دارد شکل می‌گیرد.'),
        (1800, 'روایت‌باز', 'سی ساعت — دیگر فقط رهگذر نیستی.'),
        (3600, 'ساکن روایتو', 'شصت ساعت تماشا؛ این خانه مال توست.'),
    ]
    current = tiers[0]
    next_tier = tiers[1] if len(tiers) > 1 else None
    for index, tier in enumerate(tiers):
        if total_minutes >= tier[0]:
            current = tier
            next_tier = tiers[index + 1] if index + 1 < len(tiers) else None
    remaining = None
    if next_tier:
        remaining = max(0, int(round(next_tier[0] - total_minutes)))
    return {
        'key': current[1],
        'label': current[1],
        'blurb': current[2],
        'minutes_threshold': current[0],
        'next_label': next_tier[1] if next_tier else None,
        'minutes_to_next': remaining,
    }


def _equivalents(total_minutes: float) -> list[dict]:
    film = total_minutes / 110.0
    nights = total_minutes / 120.0  # ~2h cinema night
    commute = total_minutes / 45.0  # Tehran metro ride vibe
    items = [
        {
            'id': 'films',
            'label': 'معادل فیلم سینمایی',
            'value': round(film, 1),
            'display': f'{film:.1f}'.rstrip('0').rstrip('.') if film else '0',
            'unit': 'فیلم',
        },
        {
            'id': 'nights',
            'label': 'شب سینمایی',
            'value': round(nights, 1),
            'display': f'{nights:.1f}'.rstrip('0').rstrip('.') if nights else '0',
            'unit': 'شب',
        },
        {
            'id': 'rides',
            'label': 'مسیر مترو',
            'value': round(commute, 1),
            'display': f'{commute:.1f}'.rstrip('0').rstrip('.') if commute else '0',
            'unit': 'مسیر',
        },
    ]
    return items


def build_watch_stats(user) -> dict:
    now = timezone.now()
    week_start = now - timedelta(days=7)

    lifetime = _progress_snapshots(user)
    before_week = _progress_snapshots(user, until=week_start)
    keys = set(lifetime) | set(before_week)
    durations = _duration_lookup(keys) if keys else {}

    total_minutes = 0.0
    week_minutes = 0.0
    titles_started = 0
    titles_completed = 0
    in_progress = 0

    for key, progress in lifetime.items():
        duration = durations.get(key, DEFAULT_MOVIE_MINUTES)
        minutes = _minutes_from_progress(progress, duration)
        total_minutes += minutes
        if progress >= 5:
            titles_started += 1
        if progress >= 95:
            titles_completed += 1
        elif progress >= 5:
            in_progress += 1

        prior = before_week.get(key, 0.0)
        delta_progress = max(0.0, progress - prior)
        # If title only appeared this week, prior is 0 — full credit for current progress.
        week_minutes += _minutes_from_progress(delta_progress, duration)

    total_minutes = round(total_minutes, 1)
    week_minutes = round(week_minutes, 1)
    hours = int(total_minutes // 60)
    mins = int(round(total_minutes % 60))
    week_hours = int(week_minutes // 60)
    week_mins = int(round(week_minutes % 60))

    return {
        'total_minutes': total_minutes,
        'total_hours': round(total_minutes / 60.0, 2),
        'hours': hours,
        'minutes': mins,
        'week_minutes': week_minutes,
        'week_hours_part': week_hours,
        'week_minutes_part': week_mins,
        'titles_started': titles_started,
        'titles_completed': titles_completed,
        'titles_in_progress': in_progress,
        'equivalents': _equivalents(total_minutes),
        'milestone': _milestone_for(total_minutes),
        'weekly_goal_minutes': 300,
        'source': 'activity_events',
        'generated_at': now.isoformat(),
    }
