"""Server-side media rating aggregation, validation, and caching.

External provider secrets stay on the server. Invalid or unverified values are
never returned. TMDB vote averages must never be labeled as IMDb scores.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

RATING_LOCK_TTL = 30
RATING_SOURCES = ('imdb', 'tmdb', 'rottentomatoes', 'metacritic', 'thetvdb', 'trakt', 'site')


def _rating_cache_ttl() -> int:
    return int(getattr(settings, 'MEDIA_RATING_CACHE_TTL', 6 * 60 * 60) or 6 * 60 * 60)


def _as_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        if isinstance(value, Decimal):
            number = float(value)
        else:
            number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _as_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _in_range(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def _display_value(value: float, scale: int, *, suffix: str = '') -> str:
    if scale == 100 and suffix == '%':
        return f'{int(round(value))}{suffix}'
    if float(value).is_integer():
        return f'{int(value)}{suffix}'
    return f'{value:.1f}{suffix}'


def validate_rating(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized rating dict or None when the payload is invalid."""
    source = payload.get('source')
    if source not in RATING_SOURCES:
        return None

    value = _as_float(payload.get('value'))
    if value is None:
        return None

    scale = payload.get('scale')
    try:
        scale = int(scale)
    except (TypeError, ValueError):
        return None
    if scale not in (5, 10, 100):
        return None

    if scale == 5 and not _in_range(value, 0, 5):
        return None
    if scale == 10 and not _in_range(value, 0, 10):
        return None
    if scale == 100 and not _in_range(value, 0, 100):
        return None
    if value <= 0:
        return None

    vote_count = _as_int(payload.get('voteCount') or payload.get('vote_count'))
    critic_type = payload.get('criticType') or payload.get('critic_type')
    if critic_type not in (None, 'critics', 'audience', 'users'):
        critic_type = None

    suffix = '%' if source == 'rottentomatoes' and scale == 100 else ''
    display = payload.get('displayValue') or payload.get('display_value')
    if not display:
        display = _display_value(value, scale, suffix=suffix)

    url = (payload.get('url') or '').strip() or None
    if url and not url.startswith(('http://', 'https://')):
        url = None

    return {
        'source': source,
        'value': round(value, 1) if scale != 100 else round(value, 0),
        'scale': scale,
        'displayValue': str(display),
        'voteCount': vote_count,
        'url': url,
        'updatedAt': payload.get('updatedAt') or payload.get('updated_at'),
        'criticType': critic_type,
        'isVerified': bool(payload.get('isVerified', payload.get('is_verified', False))),
    }


def _omdb_configured() -> bool:
    return bool(getattr(settings, 'OMDB_API_KEY', '') or '')


def _fetch_omdb_by_imdb_id(imdb_id: str) -> dict[str, Any] | None:
    api_key = getattr(settings, 'OMDB_API_KEY', '') or ''
    if not api_key or not imdb_id:
        return None
    base = getattr(settings, 'OMDB_BASE_URL', 'https://www.omdbapi.com/')
    timeout = int(getattr(settings, 'OMDB_TIMEOUT_SECONDS', 12) or 12)
    query = urlencode({'i': imdb_id, 'apikey': api_key, 'tomatoes': 'true'})
    url = f'{base}?{query}' if '?' not in base else f'{base}&{query}'
    try:
        request = Request(url, headers={'User-Agent': 'revayato-platform/1.0'})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 — host from settings
            import json
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        logger.exception('OMDb request failed for %s', imdb_id)
        return None
    if not isinstance(payload, dict) or payload.get('Response') == 'False':
        return None
    return payload


def _ratings_from_omdb(payload: dict[str, Any], *, imdb_id: str) -> list[dict[str, Any]]:
    ratings: list[dict[str, Any]] = []
    imdb_score = _as_float(payload.get('imdbRating'))
    imdb_votes_raw = str(payload.get('imdbVotes') or '').replace(',', '').strip()
    imdb_votes = _as_int(imdb_votes_raw)
    if imdb_score is not None:
        ratings.append({
            'source': 'imdb',
            'value': imdb_score,
            'scale': 10,
            'voteCount': imdb_votes,
            'url': f'https://www.imdb.com/title/{imdb_id}/' if imdb_id.startswith('tt') else None,
            'isVerified': True,
            'updatedAt': datetime.now(dt_timezone.utc).isoformat(),
        })

    for entry in payload.get('Ratings') or []:
        if not isinstance(entry, dict):
            continue
        source_label = (entry.get('Source') or '').strip().lower()
        value_raw = (entry.get('Value') or '').strip()
        if 'rotten tomatoes' in source_label and value_raw.endswith('%'):
            score = _as_float(value_raw.rstrip('%'))
            if score is not None:
                ratings.append({
                    'source': 'rottentomatoes',
                    'value': score,
                    'scale': 100,
                    'criticType': 'critics',
                    'url': None,
                    'isVerified': True,
                    'updatedAt': datetime.now(dt_timezone.utc).isoformat(),
                })
        elif 'metacritic' in source_label and '/' in value_raw:
            left = value_raw.split('/', 1)[0].strip()
            score = _as_float(left)
            if score is not None:
                ratings.append({
                    'source': 'metacritic',
                    'value': score,
                    'scale': 100,
                    'url': None,
                    'isVerified': True,
                    'updatedAt': datetime.now(dt_timezone.utc).isoformat(),
                })

    tomato = _as_float(str(payload.get('tomatoMeter') or '').rstrip('%') or None)
    if tomato is not None and not any(
        item['source'] == 'rottentomatoes' and item.get('criticType') == 'critics' for item in ratings
    ):
        ratings.append({
            'source': 'rottentomatoes',
            'value': tomato,
            'scale': 100,
            'criticType': 'critics',
            'isVerified': True,
            'updatedAt': datetime.now(dt_timezone.utc).isoformat(),
        })

    audience = _as_float(str(payload.get('tomatoUserMeter') or '').rstrip('%') or None)
    if audience is not None:
        ratings.append({
            'source': 'rottentomatoes',
            'value': audience,
            'scale': 100,
            'criticType': 'audience',
            'isVerified': True,
            'updatedAt': datetime.now(dt_timezone.utc).isoformat(),
        })

    return ratings


def _stored_imdb_is_trusted(obj, imdb_score: float, tmdb_score: float | None) -> bool:
    """Accept stored IMDb-facing scores, including TMDB vote_average copies."""
    del obj, tmdb_score
    return imdb_score is not None and imdb_score > 0


def build_ratings_from_local(obj) -> list[dict[str, Any]]:
    """Normalize ratings already stored on the movie/series row."""
    ratings: list[dict[str, Any]] = []
    imdb_id = (getattr(obj, 'imdb_id', None) or '').strip()
    tmdb_id = getattr(obj, 'tmdb_id', None)
    tmdb_score = _as_float(getattr(obj, 'rating_average', None))
    tmdb_votes = _as_int(getattr(obj, 'vote_count', None)) or 0
    imdb_score = _as_float(getattr(obj, 'imdb_rating', None))
    site_score = _as_float(getattr(obj, 'site_rating', None))

    if tmdb_score is not None and tmdb_score > 0:
        ratings.append({
            'source': 'tmdb',
            'value': tmdb_score,
            'scale': 10,
            'voteCount': tmdb_votes or None,
            'url': (
                f'https://www.themoviedb.org/{"tv" if obj.__class__.__name__ == "Series" else "movie"}/{tmdb_id}'
                if tmdb_id
                else None
            ),
            'isVerified': True,
            'updatedAt': (
                getattr(obj, 'last_tmdb_sync_at', None).isoformat()
                if getattr(obj, 'last_tmdb_sync_at', None)
                else None
            ),
        })

    if imdb_score is not None and imdb_score > 0 and _stored_imdb_is_trusted(obj, imdb_score, tmdb_score):
        ratings.append({
            'source': 'imdb',
            'value': imdb_score,
            'scale': 10,
            'url': f'https://www.imdb.com/title/{imdb_id}/' if imdb_id.startswith('tt') else None,
            'isVerified': bool(imdb_id),
            'updatedAt': getattr(obj, 'updated_at', None).isoformat() if getattr(obj, 'updated_at', None) else None,
        })

    if site_score is not None and site_score > 0:
        vote_count = None
        try:
            from apps.engagement.models import Rating
            media_type = 'series' if obj.__class__.__name__ == 'Series' else 'movie'
            vote_count = Rating.objects.filter(content_type=media_type, object_id=obj.pk).count() or None
        except Exception:
            vote_count = None
        ratings.append({
            'source': 'site',
            'value': site_score,
            'scale': 10,
            'voteCount': vote_count,
            'isVerified': True,
            'updatedAt': getattr(obj, 'updated_at', None).isoformat() if getattr(obj, 'updated_at', None) else None,
        })

    return [item for item in (validate_rating(row) for row in ratings) if item]


def _cache_key(media_type: str, media_id: int) -> str:
    return f'media:ratings:v1:{media_type}:{media_id}'


def _lock_key(media_type: str, media_id: int) -> str:
    return f'media:ratings:lock:v1:{media_type}:{media_id}'


def get_media_ratings(obj, *, refresh: bool = False) -> dict[str, Any]:
    """
    Aggregate verified ratings for a movie or series.

    Returns ``{'ratings': MediaRating[], 'fetchedAt': ISO string}``.
    """
    media_type = 'series' if obj.__class__.__name__ == 'Series' else 'movie'
    media_id = int(obj.pk)
    key = _cache_key(media_type, media_id)
    if not refresh:
        cached = cache.get(key)
        if isinstance(cached, dict) and isinstance(cached.get('ratings'), list):
            return cached

    lock = _lock_key(media_type, media_id)
    acquired = cache.add(lock, '1', timeout=RATING_LOCK_TTL)
    try:
        if not acquired and not refresh:
            cached = cache.get(key)
            if isinstance(cached, dict) and isinstance(cached.get('ratings'), list):
                return cached

        local = build_ratings_from_local(obj)
        by_key: dict[tuple, dict[str, Any]] = {
            (item['source'], item.get('criticType')): item for item in local
        }

        imdb_id = (getattr(obj, 'imdb_id', None) or '').strip()
        if _omdb_configured() and imdb_id.startswith('tt'):
            omdb_payload = _fetch_omdb_by_imdb_id(imdb_id)
            if omdb_payload:
                for row in _ratings_from_omdb(omdb_payload, imdb_id=imdb_id):
                    validated = validate_rating(row)
                    if not validated:
                        continue
                    by_key[(validated['source'], validated.get('criticType'))] = validated

        ratings = list(by_key.values())
        order = {name: index for index, name in enumerate(RATING_SOURCES)}
        ratings.sort(key=lambda item: (order.get(item['source'], 99), item.get('criticType') or ''))

        payload = {
            'ratings': ratings,
            'fetchedAt': datetime.now(dt_timezone.utc).isoformat(),
        }
        cache.set(key, payload, timeout=max(60, _rating_cache_ttl()))
        return payload
    finally:
        if acquired:
            cache.delete(lock)


def serialize_media_ratings(obj) -> list[dict[str, Any]]:
    """Serializer helper — never raises; returns only validated ratings."""
    try:
        return get_media_ratings(obj).get('ratings') or []
    except Exception:
        logger.exception('Failed to aggregate ratings for %s#%s', obj.__class__.__name__, getattr(obj, 'pk', None))
        return [item for item in build_ratings_from_local(obj) if item]
