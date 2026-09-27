"""Weekly airing schedule (جدول پخش هفتگی).

Built entirely from real catalog data that the importers and crawler already
populate:

* ``Episode.air_date`` — the broadcast date each series episode aired/airs on.
* ``Movie.release_date`` — treated as a premiere entry on its release day.

Only published rows on published parents are surfaced, so the schedule mirrors
exactly what a visitor can open. Nothing here fabricates dates: a title without
a real ``air_date`` simply does not appear in the schedule.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.utils import timezone

from config.public_urls import media_url

from .models import Episode, Movie

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


def _episode_entry(episode: Episode, today: datetime.date) -> dict[str, Any]:
    season = episode.season
    series = season.series
    return {
        'type': 'episode',
        'air_date': episode.air_date.isoformat(),
        'released': episode.air_date <= today,
        'series_slug': series.slug,
        'series_title': series.title,
        'series_original_title': series.original_title,
        'poster_url': _poster_url(series),
        'season_number': season.season_number,
        'episode_number': episode.episode_number,
        'episode_title': episode.title,
        'imdb_rating': _rating(series.imdb_rating),
        'content_format': series.content_format,
        'is_dubbed': series.is_dubbed,
        'has_subtitle': series.has_subtitle,
    }


def _movie_entry(movie: Movie, today: datetime.date) -> dict[str, Any]:
    return {
        'type': 'movie',
        'air_date': movie.release_date.isoformat(),
        'released': movie.release_date <= today,
        'series_slug': movie.slug,
        'series_title': movie.title,
        'series_original_title': movie.original_title,
        'poster_url': _poster_url(movie),
        'season_number': None,
        'episode_number': None,
        'episode_title': None,
        'imdb_rating': _rating(movie.imdb_rating),
        'content_format': movie.content_format,
        'is_dubbed': movie.is_dubbed,
        'has_subtitle': movie.has_subtitle,
    }


def build_weekly_schedule(
    *,
    start: datetime.date | None = None,
    days: int = DEFAULT_DAYS,
    include_movies: bool = True,
) -> dict[str, Any]:
    """Group published episodes (and movie premieres) by their air date."""
    today = timezone.localdate()
    days = max(MIN_DAYS, min(MAX_DAYS, int(days or DEFAULT_DAYS)))
    start = start or week_start_for(today)
    end = start + datetime.timedelta(days=days - 1)

    buckets: dict[datetime.date, list[dict[str, Any]]] = {
        start + datetime.timedelta(days=offset): [] for offset in range(days)
    }

    episodes = (
        Episode.objects.filter(
            is_published=True,
            season__is_published=True,
            season__series__is_published=True,
            air_date__gte=start,
            air_date__lte=end,
        )
        .select_related('season', 'season__series')
        .order_by('air_date', 'season__series__title', 'season__season_number', 'episode_number')
    )
    for episode in episodes.iterator(chunk_size=200):
        bucket = buckets.get(episode.air_date)
        if bucket is not None:
            bucket.append(_episode_entry(episode, today))

    if include_movies:
        movies = (
            Movie.objects.filter(
                is_published=True,
                release_date__gte=start,
                release_date__lte=end,
            )
            .order_by('release_date', 'title')
        )
        for movie in movies.iterator(chunk_size=200):
            bucket = buckets.get(movie.release_date)
            if bucket is not None:
                bucket.append(_movie_entry(movie, today))

    days_payload = []
    for offset in range(days):
        date = start + datetime.timedelta(days=offset)
        entries = buckets[date]
        days_payload.append({
            'date': date.isoformat(),
            'weekday': date.weekday(),
            'weekday_label': PERSIAN_WEEKDAYS.get(date.weekday(), ''),
            'is_today': date == today,
            'count': len(entries),
            'entries': entries,
        })

    return {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'today': today.isoformat(),
        'days': days_payload,
        'total': sum(day['count'] for day in days_payload),
        'generated_at': timezone.now().isoformat(),
    }
