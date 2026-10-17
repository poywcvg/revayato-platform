"""Weekly airing schedule (جدول پخش هفتگی).

Dates come from :class:`~apps.catalog.models.AiringEntry`, which
:mod:`apps.catalog.airing` fills from TMDB (each episode's ``air_date``, a
movie's digital release date) and whose ``status`` the airing hunter moves to
``available`` once the crawlers have put the release on the site. Published
episodes with a real ``air_date`` fill in for anything the sync does not track.
Nothing here fabricates a date: a release without one is not on the schedule.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.utils import timezone

from config.public_urls import media_url

from .models import AiringEntry, Episode

# Persian weekday labels keyed by Python's ``date.weekday()`` (Mon=0 … Sun=6).
PERSIAN_WEEKDAYS = {
    5: 'شنبه',
    6: 'یک‌شنبه',
    0: 'دوشنبه',
    1: 'سه‌شنبه',
    2: 'چهارشنبه',
    3: 'پنج‌شنبه',
    4: 'جمعه',
}

MIN_DAYS = 1
MAX_DAYS = 21
DEFAULT_DAYS = 7


def week_start_for(day: datetime.date) -> datetime.date:
    """Return the Saturday on/before ``day`` (Persian week starts Saturday)."""
    days_since_saturday = (day.weekday() - 5) % 7
    return day - datetime.timedelta(days=days_since_saturday)


def _poster_url(obj) -> str | None:
    poster = getattr(obj, 'poster', None)
    if poster is not None and getattr(poster, 'name', None):
        resolved = media_url(poster)
        if resolved:
            return resolved
    return (getattr(obj, 'poster_external_url', '') or '').strip() or None


def _rating(value) -> str | None:
    if value is None:
        return None
    try:
        if float(value) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    text = format(float(value), '.1f').rstrip('0').rstrip('.')
    return text or None


def _base(obj, *, kind: str) -> dict[str, Any]:
    return {
        'type': kind,
        'series_slug': obj.slug,
        'series_title': obj.title,
        'series_original_title': obj.original_title,
        'poster_url': _poster_url(obj),
        'imdb_rating': _rating(obj.imdb_rating),
        # Only a rating viewers actually gave counts; a zero-vote score is noise.
        'site_rating': _rating(obj.site_rating) if getattr(obj, 'site_rating_count', 0) else None,
        'year': getattr(obj, 'release_year', None) or getattr(obj, 'start_year', None),
        'content_format': obj.content_format,
        'is_dubbed': obj.is_dubbed,
        'has_subtitle': obj.has_subtitle,
        # A draft has no public page yet: the card shows, but does not link.
        'is_published': bool(obj.is_published),
    }


def _airing_entry(entry: AiringEntry, today: datetime.date) -> dict[str, Any]:
    is_movie = entry.kind == AiringEntry.Kind.MOVIE
    obj = entry.movie if is_movie else entry.series
    status = entry.status
    if status == AiringEntry.Status.UPCOMING and entry.air_date <= today:
        status = AiringEntry.Status.WAITING  # due today; the hunter is on it
    return {
        **_base(obj, kind='movie' if is_movie else 'episode'),
        'air_date': entry.air_date.isoformat(),
        'released': entry.air_date <= today,
        'status': status,
        'available': entry.status == AiringEntry.Status.AVAILABLE,
        'available_at': entry.available_at.isoformat() if entry.available_at else None,
        'release_type': entry.release_type or ('digital' if is_movie else 'standard'),
        'season_number': None if is_movie else entry.season_number,
        'episode_number': None if is_movie else entry.episode_number,
        'episode_title': None if is_movie else (entry.title or None),
        'still_url': entry.still_url or None,
        'network': entry.network or None,
        'runtime_minutes': entry.runtime_minutes,
        '_popularity': float(getattr(obj, 'popularity', 0) or 0),
    }


def _episode_entry(episode: Episode, today: datetime.date) -> dict[str, Any]:
    """A published episode with a real air date that the sync has no row for."""
    season = episode.season
    series = season.series
    return {
        **_base(series, kind='episode'),
        'air_date': episode.air_date.isoformat(),
        'released': episode.air_date <= today,
        'status': AiringEntry.Status.AVAILABLE,
        'available': True,
        'available_at': None,
        'release_type': 'premiere' if episode.episode_number == 1 else 'standard',
        'season_number': season.season_number,
        'episode_number': episode.episode_number,
        'episode_title': episode.title,
        'still_url': None,
        'network': None,
        'runtime_minutes': episode.duration_minutes,
        '_popularity': float(series.popularity or 0),
    }


def _watchable_episode_keys(keys: set[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
    """The (series, season, episode) keys a viewer can play or download right now."""
    if not keys:
        return set()
    rows = (
        Episode.objects.filter(
            is_published=True,
            season__is_published=True,
            season__series__is_published=True,
            season__series_id__in={key[0] for key in keys},
            episode_number__in={key[2] for key in keys},
        )
        .exclude(video_url='', download_key='')
        .values_list('season__series_id', 'season__season_number', 'episode_number')
    )
    return {tuple(row) for row in rows} & keys


def _movie_watchable(movie) -> bool:
    from .top_catalog import _has_download_links

    return bool(movie.is_published and _has_download_links(movie))


def _group_episodes(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One card per series season and day: a binge drop reads «قسمت ۱ تا ۸»."""
    grouped: dict[tuple, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for row in entries:
        if row['type'] != 'episode':
            out.append(row)
            continue
        key = (row['series_slug'], row['season_number'])
        head = grouped.get(key)
        if head is None:
            row['episode_numbers'] = [row['episode_number']]
            grouped[key] = row
            out.append(row)
            continue
        head['episode_numbers'].append(row['episode_number'])
    for head in grouped.values():
        numbers = sorted(set(head['episode_numbers']))
        head['episode_numbers'] = numbers
        if len(numbers) > 1:
            head['episode_number'] = numbers[0]
            head['episode_title'] = None
            head['still_url'] = None
    return out


def build_weekly_schedule(
    *,
    start: datetime.date | None = None,
    days: int = DEFAULT_DAYS,
    include_movies: bool = True,
    available_only: bool = False,
) -> dict[str, Any]:
    """Every dated release in the range, grouped by day.

    Dates are TMDB's (episode ``air_date``, a movie's *digital* release) kept in
    :class:`AiringEntry` by :mod:`apps.catalog.airing`, with each release's
    state on the site: upcoming, aired and being fetched, or watchable.
    Published episodes with a real air date that the sync does not track fill in
    around them. Nothing is estimated.

    ``available_only`` is the public view: only releases a viewer can play or
    download right now, re-checked against the catalog at read time (a stored
    ``available`` can go stale), one card per series season and day.
    """
    from .airing import today_tehran

    today = today_tehran()
    days = max(MIN_DAYS, min(MAX_DAYS, int(days or DEFAULT_DAYS)))
    start = start or week_start_for(today)
    end = start + datetime.timedelta(days=days - 1)
    if available_only:
        end = min(end, today)
        days = max(0, (end - start).days + 1)

    buckets: dict[datetime.date, list[dict[str, Any]]] = {
        start + datetime.timedelta(days=offset): [] for offset in range(days)
    }

    airing = (
        AiringEntry.objects.filter(air_date__gte=start, air_date__lte=end)
        .exclude(status=AiringEntry.Status.DROPPED)
        .select_related('series', 'movie')
    )
    if available_only:
        airing = airing.filter(status=AiringEntry.Status.AVAILABLE)
    if not include_movies:
        airing = airing.filter(kind=AiringEntry.Kind.EPISODE)
    rows = [entry for entry in airing.iterator(chunk_size=200) if entry.target is not None]
    watchable: set[tuple[int, int, int]] | None = None
    if available_only:
        watchable = _watchable_episode_keys({
            (entry.series_id, entry.season_number, entry.episode_number)
            for entry in rows if entry.kind == AiringEntry.Kind.EPISODE
        })
    tracked: set[tuple[int, int, int]] = set()
    for entry in rows:
        if entry.kind == AiringEntry.Kind.EPISODE:
            key = (entry.series_id, entry.season_number, entry.episode_number)
            tracked.add(key)
            if watchable is not None and key not in watchable:
                continue
        elif available_only and not _movie_watchable(entry.movie):
            continue
        bucket = buckets.get(entry.air_date)
        if bucket is not None:
            bucket.append(_airing_entry(entry, today))

    episodes = (
        Episode.objects.filter(
            is_published=True,
            season__is_published=True,
            season__series__is_published=True,
            air_date__gte=start,
            air_date__lte=end,
        )
        .select_related('season', 'season__series')
    )
    if available_only:
        episodes = episodes.exclude(video_url='', download_key='')
    for episode in episodes.iterator(chunk_size=200):
        key = (episode.season.series_id, episode.season.season_number, episode.episode_number)
        if key in tracked:
            continue
        bucket = buckets.get(episode.air_date)
        if bucket is not None:
            bucket.append(_episode_entry(episode, today))

    days_payload = []
    for offset in range(days):
        date = start + datetime.timedelta(days=offset)
        entries = sorted(
            buckets[date],
            key=lambda row: (
                -row['_popularity'], row['series_title'],
                row['season_number'] or 0, row['episode_number'] or 0,
            ),
        )
        for row in entries:
            row.pop('_popularity', None)
        if available_only:
            entries = _group_episodes(entries)
        days_payload.append({
            'date': date.isoformat(),
            'weekday': date.weekday(),
            'weekday_label': PERSIAN_WEEKDAYS.get(date.weekday(), ''),
            'is_today': date == today,
            'count': len(entries),
            'available': sum(1 for row in entries if row['available']),
            'entries': entries,
        })

    return {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'today': today.isoformat(),
        'timezone': 'Asia/Tehran',
        'days': days_payload,
        'total': sum(day['count'] for day in days_payload),
        'generated_at': timezone.now().isoformat(),
    }
