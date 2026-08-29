"""Account recommendation ranking for authenticated users.

Pipeline mirrors the on-device scorer principles in
`frontend/app/utils/recommendationScoring.ts`:

1. Collapse noisy events (progress keeps furthest point; mutable actions keep last state).
2. Build a decayed taste profile from consented events + likes/ratings/watchlist.
3. Score candidates with editorial baseline, behavior, cast/genre similarity,
   explicit preferences, and soft demotions for in-progress / completed titles.
4. Diversify with MMR + a light exploration slot.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import timedelta

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.catalog.models import Genre, Movie, MovieActor, Series, SeriesActor
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem


EVENT_WINDOW_DAYS = 90
RECENCY_HALF_LIFE_DAYS = 10
CANDIDATE_POOL_SIZE = 100
MAX_POSITIVE_CONTEXT = 14
EXPLORATION_SLOTS = 1

MOOD_GENRES = {
    'exciting': ('action', 'adventure', 'crime'),
    'calm': ('drama', 'romance', 'family'),
    'scary': ('horror', 'mystery'),
    'romantic': ('romance',),
    'thoughtful': ('sci-fi', 'mystery', 'drama'),
    'family': ('family', 'animation'),
    'light': ('comedy', 'family'),
}

LANGUAGE_ALIASES = {
    'fa': ('fa', 'فارسی', 'persian', 'farsi'),
    'en': ('en', 'انگلیسی', 'english'),
    'ko': ('ko', 'کره‌ای', 'کره ای', 'korean'),
    'fr': ('fr', 'فرانسوی', 'french'),
    'de': ('de', 'آلمانی', 'german'),
    'tr': ('tr', 'ترکی', 'turkish'),
}


def _normalize(value):
    return re.sub(
        r'\s+',
        ' ',
        str(value or '').replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک'),
    ).strip().lower()


def _add(scores, key, amount):
    key = str(key or '').strip()
    if key and amount:
        scores[key] += amount


def _squash(value):
    return math.copysign(math.log1p(abs(value)) * 3, value) if value else 0


def _recency(created_at, now):
    age_days = max(0, (now - created_at).total_seconds()) / 86400
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def _content_key(content_type, object_id):
    return content_type, int(object_id)


def _content_type(obj):
    return 'movie' if isinstance(obj, Movie) else 'series'


def _is_fresh(item):
    created = getattr(item, 'created_at', None)
    if not created:
        return False
    return (timezone.now() - created).days <= 21


def _is_trending_flag(item):
    # Backend has no is_trending column; featured + high engagement approximates it.
    return bool(getattr(item, 'is_featured', False)) or int(getattr(item, 'view_count', 0) or 0) >= 80


def _year(item):
    if isinstance(item, Movie):
        return int(getattr(item, 'release_year', None) or 0)
    return int(getattr(item, 'start_year', None) or 0)


def _duration(item):
    return int(getattr(item, 'duration_minutes', None) or 0)


def _quality_tier(item):
    """Coarse production-quality tier from the strongest available rating.

    0 = unknown, 1 = mid (below 6.0), 2 = good (6.0–7.4), 3 = excellent (7.5+).
    Used only as a light tie-break so the rail does not mix prestige and filler
    titles that would otherwise look equally "similar" on genre alone.
    """
    rating = None
    for attr in ('imdb_rating', 'rating_average', 'site_rating'):
        value = getattr(item, attr, None)
        if value is None:
            continue
        try:
            rating = float(value)
            break
        except (TypeError, ValueError):
            continue
    if rating is None:
        return 0
    if rating >= 7.5:
        return 3
    if rating >= 6.0:
        return 2
    return 1


def _cast_names(item, limit=6):
    if isinstance(item, Movie):
        roles = getattr(item, '_prefetched_objects_cache', {}).get('movie_actors')
        if roles is None:
            roles = item.movie_actors.select_related('actor').order_by('order')[:limit]
        else:
            roles = sorted(roles, key=lambda row: row.order)[:limit]
        return [row.actor.name for row in roles if getattr(row, 'actor', None) and row.actor.name]
    roles = getattr(item, '_prefetched_objects_cache', {}).get('series_actors')
    if roles is None:
        roles = item.series_actors.select_related('actor').order_by('order')[:limit]
    else:
        roles = sorted(roles, key=lambda row: row.order)[:limit]
    return [row.actor.name for row in roles if getattr(row, 'actor', None) and row.actor.name]


def _related_prefetch(model):
    if model is Movie:
        return (
            'genres',
            'directors',
            'countries',
            'tags',
            Prefetch('movie_actors', queryset=MovieActor.objects.select_related('actor').order_by('order')),
        )
    return (
        'genres',
        'directors',
        'countries',
        'tags',
        Prefetch('series_actors', queryset=SeriesActor.objects.select_related('actor').order_by('order')),
    )


def _base_queryset(model):
    from apps.catalog.trending import lean_public_queryset

    related = _related_prefetch(model)
    base = model.objects.filter(is_published=True)

    # Select cheap IDs first. The previous implementation prefetched genres,
    # directors, countries and cast four separate times, so popular/playable/
    # fresh overlap was transferred and instantiated repeatedly. Hydrate the
    # final unique pool exactly once instead.
    candidate_queries = (
        base.filter(is_featured=True).values_list('pk', flat=True)[:30],
        base.order_by(
            '-popularity', '-view_count', '-like_count', '-created_at',
        ).values_list('pk', flat=True)[:CANDIDATE_POOL_SIZE],
        base.filter(
            Q(is_dubbed=True) | Q(has_subtitle=True),
        ).order_by('-popularity', '-updated_at').values_list('pk', flat=True)[:40],
        base.order_by('-created_at').values_list('pk', flat=True)[:20],
    )
    candidate_ids = {}
    for query in candidate_queries:
        for item_id in query:
            candidate_ids[item_id] = None

    if not candidate_ids:
        return []

    hydrated = lean_public_queryset(
        base.filter(pk__in=candidate_ids),
        keep=('content_warnings',),
    ).prefetch_related(*related)
    return list(hydrated)


def _playable_boost(item):
    score = 0.0
    if getattr(item, 'is_dubbed', False):
        score += 2.6
    if getattr(item, 'has_subtitle', False):
        score += 2.2
    links = getattr(item, 'download_links', None) or []
    if isinstance(links, list) and any(isinstance(row, dict) and (row.get('url') or row.get('key')) for row in links):
        score += 3.4
    tracks = getattr(item, 'subtitle_tracks', None) or []
    if isinstance(tracks, list) and tracks:
        score += 1.8
    return score


def _load_content(keys):
    movie_ids = [object_id for content_type, object_id in keys if content_type == 'movie']
    series_ids = [object_id for content_type, object_id in keys if content_type == 'series']
    objects = {}
    if movie_ids:
        for item in Movie.objects.filter(id__in=movie_ids).prefetch_related(*_related_prefetch(Movie)):
            objects[_content_key('movie', item.id)] = item
    if series_ids:
        for item in Series.objects.filter(id__in=series_ids).prefetch_related(*_related_prefetch(Series)):
            objects[_content_key('series', item.id)] = item
    return objects


def _original_event_type(event):
    metadata = event.metadata or {}
    return str(metadata.get('event_type') or event.action or '').strip()


def _collapse_events(events):
    collapsed = {}
    for event in events:
        title_key = f'{event.content_type}:{event.object_id or ""}'
        family = ''
        if event.action in {'like', 'remove_like', 'dislike'}:
            family = 'affinity'
        elif event.action in {'add_to_watchlist', 'remove_from_watchlist'}:
            family = 'watchlist'
        elif event.action == 'rate':
            family = 'rating'

        if family and event.object_id:
            key = f'state:{family}:{title_key}'
        elif event.action == 'watch_progress' and event.object_id:
            key = f'progress:{event.session_key or "user"}:{title_key}'
        elif event.object_id:
            key = f'{event.action}:{title_key}:{event.created_at.date().isoformat()}'
        else:
            metadata = event.metadata or {}
            key = (
                f'{event.action}:{event.query}:{metadata.get("genre", "")}:'
                f'{metadata.get("filter_value", "")}:{event.created_at.date().isoformat()}'
            )

        previous = collapsed.get(key)
        if previous is None:
            collapsed[key] = event
        elif event.action == 'watch_progress':
            if (event.progress or 0) >= (previous.progress or 0):
                collapsed[key] = event
        elif event.created_at >= previous.created_at:
            collapsed[key] = event
    return sorted(collapsed.values(), key=lambda event: event.created_at)


def _event_weight(event):
    progress = max(0, min(100, event.progress or 0))
    original = _original_event_type(event)
    weights = {
        'view_movie': 0.7,
        'view_series': 0.7,
        'trailer_watch': 1.35,
        'play_trailer': 1.35,
        'play': 2.4,
        'start_watch': 2.1,
        'continue_watch': 3.4,
        'pause': 0.85 if progress >= 20 else 0.25,
        'pause_watch': 0.85 if progress >= 20 else 0.25,
        # Deep watches dominate taste — progress past 10% grows quickly.
        'watch_progress': 0 if progress < 8 else 1.2 + progress * 0.065,
        'complete_watch': 8.5,
        'add_to_watchlist': 4.5,
        'add_watchlist': 4.5,
        'remove_from_watchlist': -1,
        'remove_watchlist': -1,
        'like': 8,
        'remove_like': -0.75,
        'dislike': -10,
        'click_search_result': 1.5,
        'recommendation_click': 2.6,
        'filter_genre': 2.8,
        'click_genre': 3.4,
        'filter_apply': 1.9,
        'filter_year': 1.2,
        'filter_country': 1.6,
        'open_actor_page': 3.6,
        'click_cast': 3.6,
        'open_director_page': 3.8,
        'click_director': 3.8,
        'search': 1.0,
    }
    if event.action == 'rate' or original == 'rate':
        return (float(event.value) - 5) * 1.85
    return weights.get(original) or weights.get(event.action, 0)


def _exact_item_weight(event):
    progress = max(0, min(100, event.progress or 0))
    original = _original_event_type(event)
    weights = {
        'view_movie': 0.2,
        'view_series': 0.2,
        'click_search_result': 1.5,
        'recommendation_click': 2.4,
        'trailer_watch': 1.5,
        'play_trailer': 1.5,
        'play': -1,
        'start_watch': -1,
        'continue_watch': -4.5,
        'watch_progress': -max(1, progress * 0.12),
        'complete_watch': -75,
        'add_to_watchlist': 9,
        'add_watchlist': 9,
        'remove_from_watchlist': -14,
        'remove_watchlist': -14,
        'like': -4,
        'remove_like': -10,
        'dislike': -140,
    }
    if event.action == 'rate' or original == 'rate':
        return -5 if event.value >= 7 else -55 if event.value <= 4 else -12
    return weights.get(original) or weights.get(event.action, 0)


def _empty_profile():
    return {
        'genres': defaultdict(float),
        'directors': defaultdict(float),
        'cast': defaultdict(float),
        'countries': defaultdict(float),
        'languages': defaultdict(float),
        'formats': defaultdict(float),
        'content_types': defaultdict(float),
        'playback': defaultdict(float),
        'items': defaultdict(float),
        'progress': {},
        'completed': set(),
        'disliked': set(),
        'positive_items': [],
        'evidence': 0.0,
        'preferred_duration': None,
        'preferred_year': None,
        'demand_genres': defaultdict(float),
    }


def _default_preferences():
    return {
        'favorite_genres': [],
        'disliked_genres': [],
        'preferred_countries': [],
        'preferred_languages': [],
        'preferred_age_ratings': [],
        'playback_preference': 'any',
        'content_sensitivity': 'any',
    }


def normalize_preferences(raw=None):
    prefs = _default_preferences()
    if not isinstance(raw, dict):
        return prefs

    def _list(value, limit=24):
        if isinstance(value, str):
            value = [part.strip() for part in value.split(',')]
        if not isinstance(value, (list, tuple)):
            return []
        cleaned = []
        for item in value:
            text = str(item or '').strip()
            if text and text not in cleaned:
                cleaned.append(text)
            if len(cleaned) >= limit:
                break
        return cleaned

    prefs['favorite_genres'] = _list(raw.get('favorite_genres'))
    prefs['disliked_genres'] = _list(raw.get('disliked_genres'))
    prefs['preferred_countries'] = [_normalize(item) for item in _list(raw.get('preferred_countries'), 16)]
    prefs['preferred_languages'] = _list(raw.get('preferred_languages'), 12)
    prefs['preferred_age_ratings'] = [
        item for item in _list(raw.get('preferred_age_ratings'), 3) if item in {'12+', '15+', '18+'}
    ]
    playback = str(raw.get('playback_preference') or 'any')
    prefs['playback_preference'] = playback if playback in {'any', 'original', 'subtitle', 'dubbed'} else 'any'
    sensitivity = str(raw.get('content_sensitivity') or 'any')
    prefs['content_sensitivity'] = sensitivity if sensitivity in {'any', 'standard', 'reduced'} else 'any'
    return prefs


def _language_match(value, preferences):
    normalized = _normalize(value)
    if not normalized or not preferences:
        return False
    for preference in preferences:
        aliases = LANGUAGE_ALIASES.get(preference, (_normalize(preference),))
        if any(alias and alias in normalized for alias in aliases):
            return True
    return False


def _country_match(item, preferences):
    if not preferences:
        return False
    names = [_normalize(country.name) for country in item.countries.all()]
    return any(any(pref in name or name in pref for name in names if name) for pref in preferences)


def _add_content_features(profile, item, weight):
    for genre in item.genres.all():
        _add(profile['genres'], genre.slug, weight)
    for director in item.directors.all():
        _add(profile['directors'], director.name, weight * 0.75)
    for actor_name in _cast_names(item, limit=5):
        _add(profile['cast'], actor_name, weight * 0.28)
    for country in item.countries.all():
        _add(profile['countries'], _normalize(country.name), weight * 0.4)
    _add(profile['languages'], _normalize(item.language), weight * 0.35)
    _add(profile['formats'], item.content_format, weight * 0.5)
    _add(profile['content_types'], _content_type(item), weight * 0.55)
    if getattr(item, 'is_dubbed', False):
        _add(profile['playback'], 'dubbed', weight * 0.55)
    if getattr(item, 'has_subtitle', False):
        _add(profile['playback'], 'subtitle', weight * 0.45)


def _remember_positive(profile, item, weight, *, duration_acc, year_acc):
    if weight < 1.4:
        return duration_acc, year_acc
    if item not in profile['positive_items']:
        profile['positive_items'].append(item)
        profile['positive_items'] = profile['positive_items'][-MAX_POSITIVE_CONTEXT:]
    duration = _duration(item)
    year = _year(item)
    if duration:
        duration_acc[0] += duration * weight
        duration_acc[1] += weight
    if year:
        year_acc[0] += year * weight
        year_acc[1] += weight
    return duration_acc, year_acc


def _apply_filter_signal(profile, event, weight):
    metadata = event.metadata or {}
    name = metadata.get('filter_name') or ''
    value = str(metadata.get('filter_value') or '').strip()
    if event.action == 'filter_genre' or _original_event_type(event) in {'click_genre', 'filter_apply'}:
        if name == 'genre' and value:
            _add(profile['genres'], value, weight)
        if name == 'content_type' and value in {'movie', 'series'}:
            _add(profile['content_types'], value, weight)
        if name == 'format' and value:
            _add(profile['formats'], value, weight)
        if name == 'availability' and value in {'dubbed', 'subtitle'}:
            _add(profile['playback'], value, weight)
        if name == 'home_category':
            if value.startswith('genre:'):
                _add(profile['genres'], value[6:], weight)
            if value in {'movie', 'series'}:
                _add(profile['content_types'], value, weight)
            if value == 'animation':
                _add(profile['formats'], value, weight)
            if value in {'dubbed', 'subtitle'}:
                _add(profile['playback'], value, weight)
        if name == 'mood':
            for genre in MOOD_GENRES.get(value, ()):
                _add(profile['genres'], genre, weight / 2)
        if not name and value:
            _add(profile['genres'], value.removeprefix('genre:'), weight)
    if event.action == 'filter_country' and value:
        _add(profile['countries'], _normalize(value), weight)
    if event.action == 'filter_year' and value.isdigit():
        # Soft year interest — prefer nearby release years later via preferred_year.
        profile.setdefault('_year_hints', [])
        profile['_year_hints'].append((int(value), weight))


def _query_match_boost(item, normalized_query):
    if not normalized_query:
        return 0
    score = 0
    title = _normalize(item.title)
    original = _normalize(getattr(item, 'original_title', ''))
    if (title and title in normalized_query) or (original and original in normalized_query):
        score += 4
    if any(_normalize(genre.title) in normalized_query or genre.slug in normalized_query for genre in item.genres.all()):
        score += 2
    if any(_normalize(director.name) in normalized_query for director in item.directors.all()):
        score += 2.5
    if any(_normalize(name) in normalized_query for name in _cast_names(item, limit=5)):
        score += 2
    if any(_normalize(country.name) in normalized_query for country in item.countries.all()):
        score += 1
    if _normalize(item.language) and _normalize(item.language) in normalized_query:
        score += 1
    return score


def _event_queryset(user):
    if not user or not user.is_authenticated:
        return UserActivityEvent.objects.none()
    return UserActivityEvent.objects.filter(
        user=user,
        created_at__gte=timezone.now() - timedelta(days=EVENT_WINDOW_DAYS),
    ).order_by('created_at')


def _seed_demand_genres(profile, candidates):
    ranked = sorted(
        candidates,
        key=lambda item: (
            int(_is_trending_flag(item)),
            float(getattr(item, 'popularity', 0) or 0),
            int(getattr(item, 'view_count', 0) or 0),
        ),
        reverse=True,
    )[:24]
    for index, item in enumerate(ranked):
        weight = max(0.2, 1.4 - index * 0.04)
        for genre in item.genres.all():
            _add(profile['demand_genres'], genre.slug, weight)


def _build_profile(user, catalog_lookup, candidates):
    profile = _empty_profile()
    now = timezone.now()
    events = list(_event_queryset(user))
    event_keys = {
        _content_key(event.content_type, event.object_id)
        for event in events
        if event.content_type in {'movie', 'series'} and event.object_id
    }

    engagement_pairs = set()
    ratings = []
    if user and user.is_authenticated:
        engagement_pairs |= set(Like.objects.filter(user=user).values_list('content_type', 'object_id'))
        engagement_pairs |= set(WatchlistItem.objects.filter(user=user).values_list('content_type', 'object_id'))
        ratings = list(Rating.objects.filter(user=user))
        engagement_pairs |= {(rating.content_type, rating.object_id) for rating in ratings}

    missing = (event_keys | engagement_pairs) - set(catalog_lookup)
    catalog_lookup.update(_load_content(missing))

    duration_acc = [0.0, 0.0]
    year_acc = [0.0, 0.0]

    for event in _collapse_events(events):
        recency = _recency(event.created_at, now)
        weight = _event_weight(event) * recency
        profile['evidence'] += min(6, abs(weight))
        metadata = event.metadata or {}
        genre = metadata.get('genre')
        if genre:
            _add(profile['genres'], genre, weight or 2 * recency)

        original = _original_event_type(event)
        if event.action in {'filter_genre', 'filter_year', 'filter_country'} or original in {
            'filter_apply', 'click_genre',
        }:
            _apply_filter_signal(profile, event, weight)
        if event.action == 'open_director_page' or original == 'click_director':
            _add(profile['directors'], metadata.get('filter_value'), weight)
        if event.action == 'open_actor_page' or original == 'click_cast':
            _add(profile['cast'], metadata.get('filter_value'), weight)

        if (event.action == 'search' or original in {'search', 'empty_search'}) and event.query:
            query = _normalize(event.query)
            matches = []
            for item in catalog_lookup.values():
                boost = _query_match_boost(item, query)
                if boost > 0:
                    matches.append((item, boost))
            matches.sort(key=lambda row: row[1], reverse=True)
            for item, boost in matches[:4]:
                search_weight = weight * min(1.4, boost / 2.5)
                _add_content_features(profile, item, search_weight)
                key = _content_key(_content_type(item), item.id)
                profile['items'][key] += search_weight * 0.3

        key = (
            _content_key(event.content_type, event.object_id)
            if event.content_type in {'movie', 'series'} and event.object_id
            else None
        )
        item = catalog_lookup.get(key) if key else None
        if item:
            _add_content_features(profile, item, weight)
            profile['items'][key] += _exact_item_weight(event) * recency
            progress = max(0, min(100, event.progress or 0))
            if progress:
                profile['progress'][key] = max(profile['progress'].get(key, 0), progress)
            duration_acc, year_acc = _remember_positive(profile, item, weight, duration_acc=duration_acc, year_acc=year_acc)
            if event.action == 'complete_watch' or original == 'complete_watch':
                profile['completed'].add(key)
            if event.action == 'dislike' or original == 'dislike' or (event.action == 'rate' and event.value <= 3):
                profile['disliked'].add(key)
            if event.action == 'like' or original == 'like':
                profile['disliked'].discard(key)

    if user and user.is_authenticated:
        for content_type, object_id in Like.objects.filter(user=user).values_list('content_type', 'object_id'):
            key = _content_key(content_type, object_id)
            if key in catalog_lookup:
                item = catalog_lookup[key]
                _add_content_features(profile, item, 7)
                profile['items'][key] -= 4
                duration_acc, year_acc = _remember_positive(profile, item, 7, duration_acc=duration_acc, year_acc=year_acc)
                profile['evidence'] += 4
        for content_type, object_id in WatchlistItem.objects.filter(user=user).values_list('content_type', 'object_id'):
            key = _content_key(content_type, object_id)
            if key in catalog_lookup:
                item = catalog_lookup[key]
                _add_content_features(profile, item, 4)
                profile['items'][key] += 9
                duration_acc, year_acc = _remember_positive(profile, item, 4, duration_acc=duration_acc, year_acc=year_acc)
                profile['evidence'] += 3
        for rating in ratings:
            key = _content_key(rating.content_type, rating.object_id)
            if key in catalog_lookup:
                item = catalog_lookup[key]
                weight = (float(rating.score) - 5) * 1.6
                _add_content_features(profile, item, weight)
                profile['evidence'] += min(6, abs(weight))
                duration_acc, year_acc = _remember_positive(profile, item, weight, duration_acc=duration_acc, year_acc=year_acc)
                if rating.score <= 3:
                    profile['disliked'].add(key)

    genre_rows = list(Genre.objects.values_list('slug', 'title'))
    for event in events:
        query = _normalize(event.query)
        if not query:
            continue
        for slug, title in genre_rows:
            if _normalize(title) in query or _normalize(slug) in query:
                _add(profile['genres'], slug, 0.8 * _recency(event.created_at, now))

    for year, weight in profile.pop('_year_hints', []):
        year_acc[0] += year * weight
        year_acc[1] += weight

    if duration_acc[1] >= 2:
        profile['preferred_duration'] = duration_acc[0] / duration_acc[1]
    if year_acc[1] >= 2:
        profile['preferred_year'] = year_acc[0] / year_acc[1]

    _seed_demand_genres(profile, candidates)
    profile['confidence'] = min(1, 1 - math.exp(-profile['evidence'] / 11))
    profile['signal_count'] = len(events) + len(engagement_pairs)
    return profile


def _taste_summary(profile):
    """Human-readable auto-detected taste for the profile UI — no questions asked."""
    genre_lookup = {
        slug: title
        for slug, title in Genre.objects.values_list('slug', 'title')
    }
    top_genres = [
        {'slug': slug, 'title': genre_lookup.get(slug, slug), 'score': round(score, 2)}
        for slug, score in sorted(profile['genres'].items(), key=lambda row: -row[1])[:5]
        if score >= 1.5
    ]
    dubbed = profile['playback'].get('dubbed', 0)
    subtitle = profile['playback'].get('subtitle', 0)
    playback = 'any'
    if dubbed > subtitle * 1.35 and dubbed >= 2.5:
        playback = 'dubbed'
    elif subtitle > dubbed * 1.35 and subtitle >= 2.5:
        playback = 'subtitle'
    return {
        'top_genres': top_genres,
        'inferred_playback': playback,
        'completed_count': len(profile['completed']),
        'mode': 'automatic',
    }


def _effective_preferences(profile, preferences):
    """Fill empty explicit prefs from observed behavior so login alone is enough."""
    prefs = {
        'favorite_genres': list(preferences.get('favorite_genres') or []),
        'disliked_genres': list(preferences.get('disliked_genres') or []),
        'preferred_countries': list(preferences.get('preferred_countries') or []),
        'preferred_languages': list(preferences.get('preferred_languages') or []),
        'preferred_age_ratings': list(preferences.get('preferred_age_ratings') or []),
        'playback_preference': preferences.get('playback_preference') or 'any',
        'content_sensitivity': preferences.get('content_sensitivity') or 'any',
        'inferred_genres': [],
        'inferred_from_behavior': False,
    }

    if not prefs['favorite_genres']:
        prefs['inferred_genres'] = [
            slug
            for slug, score in sorted(profile['genres'].items(), key=lambda row: -row[1])[:4]
            if score >= 2.5
        ]
        prefs['inferred_from_behavior'] = bool(prefs['inferred_genres'])

    if prefs['playback_preference'] == 'any':
        dubbed = profile['playback'].get('dubbed', 0)
        subtitle = profile['playback'].get('subtitle', 0)
        if dubbed > subtitle * 1.4 and dubbed >= 3:
            prefs['playback_preference'] = 'dubbed'
            prefs['inferred_from_behavior'] = True
        elif subtitle > dubbed * 1.4 and subtitle >= 3:
            prefs['playback_preference'] = 'subtitle'
            prefs['inferred_from_behavior'] = True

    if not prefs['preferred_countries']:
        prefs['preferred_countries'] = [
            name
            for name, score in sorted(profile['countries'].items(), key=lambda row: -row[1])[:3]
            if score >= 2.5
        ]
        if prefs['preferred_countries']:
            prefs['inferred_from_behavior'] = True

    return prefs


def _rating(item):
    return float(
        getattr(item, 'imdb_rating', None)
        or getattr(item, 'site_rating', None)
        or getattr(item, 'tmdb_rating', None)
        or 0
    )


def _playback_pref_score(item, preference):
    if preference == 'dubbed':
        return 7 if getattr(item, 'is_dubbed', False) else -2
    if preference == 'subtitle':
        return 5 if getattr(item, 'has_subtitle', False) else -2
    if preference == 'original':
        return 0 if getattr(item, 'is_dubbed', False) else 2
    return 0


def _sensitivity_score(item, preference):
    warnings = getattr(item, 'content_warnings', None) or []
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    if preference == 'reduced':
        return (
            (-28 if getattr(item, 'is_uncensored', False) else 0)
            + (-14 if getattr(item, 'age_rating', '') == '18+' else 0)
            - min(12, warning_count * 3)
        )
    if preference == 'standard':
        return (-5 if getattr(item, 'is_uncensored', False) else 0) - min(4, warning_count)
    return 0


def _jaccard(first, second):
    if not first or not second:
        return 0
    intersection = len(first & second)
    union = len(first | second)
    return intersection / union if union else 0


def _year_distance(first_year, second_year):
    """~1.0 when years are close, decaying to 0 beyond ~12 years apart."""
    if not first_year or not second_year:
        return 0.0
    delta = abs(int(first_year) - int(second_year))
    if delta <= 1:
        return 1.0
    if delta >= 12:
        return 0.0
    return 1.0 - (delta - 1) / 11


_BROAD_GENRES = frozenset({'drama', 'comedy', 'romance', 'thriller'})


def _normalized_language(item):
    lang = _normalize(getattr(item, 'original_language', '') or '')
    if not lang:
        lang = _normalize(getattr(item, 'language', '') or '')
    return lang


def _genre_overlap(first, second):
    """Genre similarity that rewards specific shared genres over broad ones.

    ``drama``/``comedy``/``romance``/``thriller`` describe thousands of titles
    each, so two titles sharing only those are common but not really "similar".
    Every shared genre counts at its full weight; sharing a specific genre in
    addition to a broad one is worth more than another broad one.

    The source's most distinctive genre must survive too: Scream (horror/crime/
    mystery) shares crime+mystery with Ace Ventura (comedy/crime/mystery), but
    Scream's horror DNA is absent, so the pair must not rank as a strong match.
    """
    first_slugs = [genre.slug for genre in first.genres.all()]
    second_slugs = [genre.slug for genre in second.genres.all()]
    first_set = set(first_slugs)
    second_set = set(second_slugs)
    intersection = first_set & second_set
    if not intersection:
        return 0.0
    union = first_set | second_set
    jaccard = len(intersection) / len(union) if union else 0.0
    specific = sum(1 for slug in intersection if slug not in _BROAD_GENRES)
    raw = min(1.0, jaccard * 0.8 + specific * 0.15)

    # The source's least-broad genre is its distinguishing identity (horror for
    # Scream, sci-fi for Arrival). Losing it halves the genre contribution so a
    # weak multi-genre overlap cannot masquerade as a real match.
    source_specific = [slug for slug in first_slugs if slug not in _BROAD_GENRES]
    if source_specific and not (source_specific[0] in intersection):
        raw *= 0.5
    return raw


def _cast_overlap(first, second):
    """Weighted shared-cast similarity that values leads (first on the order).

    Top-billed actors reflect the creative DNA of a title far more than
    supporting players, so their matches dominate the score.
    """
    first_names = _cast_names(first, limit=6)
    second_names = _cast_names(second, limit=6)
    second_set = set(second_names)
    shared = [(index, name) for index, name in enumerate(first_names) if name in second_set]
    if not shared:
        return 0.0
    # index 0..5 -> 1.0, 0.7, 0.5, 0.4, 0.33, 0.28; average across shared seats.
    weights = [1.0, 0.7, 0.5, 0.4, 0.33, 0.28]
    total = sum(weights[min(index, len(weights) - 1)] for index, _name in shared) / len(first_names or [1])
    return min(1.0, total * 1.25)


def _title_token_match(first, second):
    """Franchise/sequel signal: same original or localized title tokens.

    Scream (1996) and Scream 7 already share genre+cast; identical original
    titles (or a shared distinctive word) push them far above genre-only peers.
    """
    first_title = _normalize(getattr(first, 'original_title', '') or '') or _normalize(first.title)
    second_title = _normalize(getattr(second, 'original_title', '') or '') or _normalize(second.title)
    if not first_title or not second_title:
        return 0.0
    if first_title == second_title:
        return 0.6
    first_tokens = {token for token in re.split(r'[^a-z0-9]+', first_title) if len(token) >= 3}
    second_tokens = {token for token in re.split(r'[^a-z0-9]+', second_title) if len(token) >= 3}
    if first_tokens & second_tokens:
        return 0.2
    return 0.0


def _similarity(first, second):
    """Pairwise content similarity shared by the similar rail and the
    personalized recommender.

    Additive (genre-dominant, like the previous scorer) so the shared
    ``0.30``/``0.35`` thresholds keep their meaning, but enriched with signals
    that were previously ignored (tags, year, country/language, quality tier,
    franchise title tokens) and re-weighted so genuinely-similar titles rank
    above weak broad-genre matches:

      * specific genre overlap ... 0.58  (broad genres de-emphasized)
      * franchise title match .... 0.30  (same original title / shared token)
      * tag Jaccard .............. 0.18  (franchise tag; sparse but decisive)
      * weighted cast overlap .... 0.16  (lead actors dominate)
      * shared director .......... 0.12
      * year proximity ........... 0.08
      * country / language ....... 0.05
      * shared content format .... +0.04
      * same quality tier ........ +0.03
    """
    genre_sim = _genre_overlap(first, second)

    first_tags = {tag.slug for tag in first.tags.all()}
    second_tags = {tag.slug for tag in second.tags.all()}
    tag_sim = _jaccard(first_tags, second_tags)

    cast_sim = _cast_overlap(first, second)
    title_sim = _title_token_match(first, second)

    first_directors = {director.name for director in first.directors.all()}
    second_directors = {director.name for director in second.directors.all()}
    director_hit = 1.0 if (first_directors & second_directors) else 0.0

    year_sim = _year_distance(_year(first), _year(second))

    first_countries = {_normalize(c.name) for c in first.countries.all()}
    second_countries = {_normalize(c.name) for c in second.countries.all()}
    country_sim = _jaccard(first_countries, second_countries)
    lang_sim = 1.0 if _normalized_language(first) and _normalized_language(first) == _normalized_language(second) else 0.0
    region_sim = max(country_sim, lang_sim)

    quality_sim = 1.0 if _quality_tier(first) == _quality_tier(second) else 0.0

    return (
        genre_sim * 0.58
        + title_sim * 0.30
        + tag_sim * 0.18
        + cast_sim * 0.16
        + director_hit * 0.12
        + year_sim * 0.08
        + region_sim * 0.05
        + (0.04 if first.content_format == second.content_format else 0)
        + (0.03 if quality_sim else 0)
    )


_SIMILAR_MIN_SCORE = 0.26
# Zero-signal sources (no genres/cast/director) fall back to the broad pool.
# Only accept genuinely strong ties there so the rail reports an honest empty
# result instead of pretending an unrelated blockbuster is "similar".
_SIMILAR_FALLBACK_MIN_SCORE = 0.30
_ACTOR_FIELD = {'Movie': 'movie_actors', 'Series': 'series_actors'}


def _similar_candidate_pool(instance, model, *, pool_size: int = 220) -> list:
    """Same-type published titles sharing at least one genre, cast member,
    director, or franchise tag with ``instance`` (view-ranked).

    The old implementation filtered on shared genre *only*, which hid every
    candidate for titles whose genre mapping was empty or sparse (common for
    brand-new 2026 imports). Broadening to cast/director/tag ties lets a
    director's or actor's other work surface even when genres are missing.
    """
    from apps.catalog.trending import lean_public_queryset

    related = _related_prefetch(model)
    base = model.objects.filter(is_published=True).exclude(pk=instance.pk)

    def _ids(queryset, limit):
        return list(queryset.values_list('pk', flat=True)[:limit])

    genre_ids = list(instance.genres.values_list('id', flat=True))
    actor_field = _ACTOR_FIELD.get(model.__name__, 'movie_actors')
    actor_ids = list(getattr(instance, actor_field).values_list('actor_id', flat=True))
    director_ids = list(instance.directors.values_list('id', flat=True))
    tag_ids = list(instance.tags.values_list('id', flat=True))

    # Signal-union candidate set (dedup by PK).
    merged: dict[int, None] = {}
    if genre_ids:
        for pk in _ids(
            base.filter(genres__in=genre_ids).order_by('-view_count', '-like_count', '-popularity'),
            pool_size,
        ):
            merged[pk] = None
    if actor_ids:
        for pk in _ids(
            base.filter(**{f'{actor_field}__actor_id__in': actor_ids})
            .order_by('-view_count', '-like_count', '-popularity')[:pool_size],
            pool_size,
        ):
            merged[pk] = None
    if director_ids:
        for pk in _ids(
            base.filter(directors__id__in=director_ids)
            .order_by('-view_count', '-like_count', '-popularity')[:pool_size],
            pool_size,
        ):
            merged[pk] = None
    if tag_ids:
        for pk in _ids(
            base.filter(tags__id__in=tag_ids)
            .order_by('-view_count', '-like_count', '-popularity')[: max(40, pool_size // 3)],
            max(40, pool_size // 3),
        ):
            merged[pk] = None

    fallback = False
    if not merged:
        # Zero signals at all — fall back to the broad same-type pool by views.
        for pk in _ids(
            base.order_by('-view_count', '-like_count', '-popularity'),
            pool_size,
        ):
            merged[pk] = None
        fallback = True
        if not merged:
            return [], True

    # Preserve view-ranked order for the scoring pass. ``original_language`` is
    # deferred by ``lean_public_queryset`` but read by ``_similarity``.
    ordered = model.objects.filter(pk__in=list(merged)).order_by(
        '-view_count', '-like_count', '-popularity',
    ).prefetch_related(*related)
    items = list(lean_public_queryset(ordered, keep=('original_language',)))
    # Tag the pool so _similar_content can require a stronger tie for the
    # unfiltered fallback (see _SIMILAR_FALLBACK_MIN_SCORE).
    return (items, fallback)


def _similar_content(instance, limit=8):
    """Return published titles of the same type that are genuinely similar.

    Deterministic per title (no user profile), so the result is safe to cache
    at the API layer. Reuses ``_similarity`` (specific-genre overlap + cast/
    director + franchise tag + title tokens + year/country) and the shared
    ``_related_prefetch`` hydration.
    """
    model = instance.__class__
    related = _related_prefetch(model)
    candidates, fallback = _similar_candidate_pool(instance, model)

    if not candidates:
        return []

    # Hydrate the source's relations too, so _similarity reads every genre/
    # director/cast set from the prefetch cache instead of re-querying them
    # once per candidate. If the caller already passed a prefetched instance
    # (the API views do), this is a no-op.
    if not getattr(instance, '_prefetched_objects_cache', None):
        instance = model.objects.prefetch_related(*related).get(pk=instance.pk)

    min_score = _SIMILAR_FALLBACK_MIN_SCORE if fallback else _SIMILAR_MIN_SCORE
    scored = [
        (score, candidate)
        for candidate in candidates
        if (score := _similarity(instance, candidate)) >= min_score
    ]
    scored.sort(key=lambda row: (-row[0], row[1].pk))
    selected = [candidate for _score, candidate in scored[:limit]]

    # Guarantee a non-empty rail for every published title. Signal-weak titles
    # (empty genres/cast/director/tags) occasionally score nothing above the
    # fallback bar, but users expect a "similar" rail on every detail page.
    # Fill from the same-type pool ranked by quality/popularity when the scored
    # set is short, preferring unaffected candidates so the rail isn't just the
    # source's own siblings.
    if len(selected) < limit:
        selected_pks = {candidate.pk for candidate in selected}
        source_pk = instance.pk
        # Reuse the already-hydrated pool, but quality-rank it; never return a
        # candidate identical to the source title.
        pool = [
            candidate for candidate in candidates
            if candidate.pk not in selected_pks and candidate.pk != source_pk
        ]
        pool.sort(key=lambda candidate: (
            -float(getattr(candidate, 'rating', 0) or 0),
            -int(getattr(candidate, 'view_count', 0) or 0),
            -int(getattr(candidate, 'popularity', 0) or 0),
            candidate.pk,
        ))
        selected.extend(pool[: limit - len(selected)])

    return selected[:limit]


def _reason_for(item, profile, preferences, best_genre, best_genre_score, best_director, best_director_score, best_cast, best_cast_score):
    recent_similar = None
    for context in reversed(profile['positive_items']):
        if context.pk == item.pk and _content_type(context) == _content_type(item):
            continue
        if _similarity(item, context) >= 0.35:
            recent_similar = context
            break

    favorite_genre = next(
        (genre for genre in item.genres.all() if genre.slug in preferences['favorite_genres']),
        None,
    )
    inferred_genre = next(
        (genre for genre in item.genres.all() if genre.slug in (preferences.get('inferred_genres') or [])),
        None,
    )
    if favorite_genre:
        return f'چون به ژانر {favorite_genre.title} علاقه داری'
    if best_cast and best_cast_score >= 1.8:
        return f'با حضور {best_cast}'
    if best_director and best_director_score >= 1.8:
        return f'از {best_director.name}'
    if best_genre and best_genre_score >= 1.8:
        return f'در حال‌وهوای {best_genre.title}'
    if recent_similar:
        return f'نزدیک به «{recent_similar.title}»'
    if inferred_genre:
        return f'نزدیک به ژانر {inferred_genre.title} که دوست داری'
    if preferences['playback_preference'] == 'dubbed' and getattr(item, 'is_dubbed', False):
        return 'با دوبله فارسی'
    if preferences['playback_preference'] == 'subtitle' and getattr(item, 'has_subtitle', False):
        return 'با زیرنویس فارسی'
    if _country_match(item, preferences['preferred_countries']):
        return 'از کشورهای موردعلاقه‌ات'
    if _language_match(item.language, preferences['preferred_languages']):
        return 'هم‌زبان با سلیقه تو'
    if getattr(item, 'is_dubbed', False):
        return 'دوبله فارسی'
    if getattr(item, 'has_subtitle', False):
        return 'زیرنویس فارسی'
    if item.is_featured or _is_trending_flag(item):
        return 'از انتخاب‌های امروز'
    return 'پیشنهاد روایتو'


def _score_item(item, profile, preferences):
    key = _content_key(_content_type(item), item.id)
    confidence = profile['confidence']
    has_explicit_taste = bool(
        preferences['favorite_genres']
        or preferences['disliked_genres']
        or preferences['preferred_countries']
        or preferences['preferred_languages']
        or preferences['playback_preference'] != 'any'
    )
    score = _rating(item) * 1.25
    score += math.log1p(item.view_count) * 0.55
    score += math.log1p(item.like_count) * 0.7
    score += math.log1p(float(getattr(item, 'popularity', 0) or 0)) * 0.5
    # Editorial boost shrinks as personalization confidence grows,
    # and shrinks further when the user stated explicit taste prefs.
    editorial_scale = max(0.18, 1 - confidence * 0.75)
    if has_explicit_taste:
        editorial_scale *= 0.4
    score += (6.5 if item.is_featured else 0) * editorial_scale
    score += (3.0 if _is_trending_flag(item) else 0) * editorial_scale
    score += 2.2 if getattr(item, 'is_recommended', False) else 0
    score += 1.0 if _is_fresh(item) else 0
    score += _playable_boost(item)
    score += profile['items'].get(key, 0)
    score += _playback_pref_score(item, preferences['playback_preference'])
    score += _sensitivity_score(item, preferences['content_sensitivity'])

    if _country_match(item, preferences['preferred_countries']):
        score += 6
    if _language_match(item.language, preferences['preferred_languages']):
        score += 5
    age = getattr(item, 'age_rating', '') or ''
    if age in preferences['preferred_age_ratings']:
        score += 4
    elif preferences['preferred_age_ratings']:
        score -= 2

    behavior = _squash(profile['content_types'].get(_content_type(item), 0)) * 0.75
    best_genre = None
    best_genre_score = 0
    for genre in item.genres.all():
        if genre.slug in preferences['favorite_genres']:
            score += 22
        elif genre.slug in (preferences.get('inferred_genres') or []):
            score += 9
        if genre.slug in preferences['disliked_genres']:
            score -= 28
        genre_score = profile['genres'].get(genre.slug, 0)
        behavior += _squash(genre_score) * 1.28
        # Demand is only a light cold-start nudge — never drown explicit favorites.
        demand_scale = 0.25 if has_explicit_taste else 1.0
        score += profile['demand_genres'].get(genre.slug, 0) * demand_scale
        if genre_score > best_genre_score:
            best_genre = genre
            best_genre_score = genre_score

    best_director = None
    best_director_score = 0
    for director in item.directors.all():
        director_score = profile['directors'].get(director.name, 0)
        behavior += _squash(director_score) * 0.95
        if director_score > best_director_score:
            best_director = director
            best_director_score = director_score

    best_cast = None
    best_cast_score = 0
    for actor_name in _cast_names(item, limit=5):
        cast_score = profile['cast'].get(actor_name, 0)
        behavior += _squash(cast_score) * 0.38
        if cast_score > best_cast_score:
            best_cast = actor_name
            best_cast_score = cast_score

    for country in item.countries.all():
        behavior += _squash(profile['countries'].get(_normalize(country.name), 0)) * 0.45
    behavior += _squash(profile['languages'].get(_normalize(item.language), 0)) * 0.45
    behavior += _squash(profile['formats'].get(item.content_format, 0)) * 0.65
    if getattr(item, 'is_dubbed', False):
        behavior += _squash(profile['playback'].get('dubbed', 0)) * 0.8
    if getattr(item, 'has_subtitle', False):
        behavior += _squash(profile['playback'].get('subtitle', 0)) * 0.7

    score += behavior * (0.62 + confidence * 0.72)

    context_similarity = max(
        (
            _similarity(item, context)
            for context in profile['positive_items']
            if not (context.pk == item.pk and _content_type(context) == _content_type(item))
        ),
        default=0,
    )
    score += context_similarity * (9.0 + confidence * 8.5)

    preferred_duration = profile['preferred_duration']
    if preferred_duration and _duration(item):
        score += max(-1.5, 2.2 - abs(_duration(item) - preferred_duration) / 28)
    preferred_year = profile['preferred_year']
    if preferred_year and _year(item):
        score += max(-1, 1.4 - abs(_year(item) - preferred_year) / 5)

    progress = profile['progress'].get(key, 0)
    score -= progress * 0.045

    if confidence < 0.2:
        score += 3.5 if item.is_featured or _is_trending_flag(item) else 0
        score += _playable_boost(item) * 0.4

    if key in profile['completed']:
        score -= 28
    if key in profile['disliked']:
        score -= 100

    reason = _reason_for(
        item,
        profile,
        preferences,
        best_genre,
        best_genre_score,
        best_director,
        best_director_score,
        best_cast,
        best_cast_score,
    )
    return {
        'item': item,
        'content_type': _content_type(item),
        'score': round(score, 3),
        'reason': reason,
    }


def _diversify(ranked, limit):
    pool = ranked[:max(limit * 4, limit)]
    selected = []
    while pool and len(selected) < limit:
        explore = len(selected) >= max(1, limit - EXPLORATION_SLOTS)

        def adjusted(candidate):
            overlap = max((_similarity(candidate['item'], chosen['item']) for chosen in selected), default=0)
            novelty = 0.0
            if explore:
                item = candidate['item']
                novelty = (
                    (1.4 if _is_fresh(item) else 0)
                    + (0.8 if _is_trending_flag(item) else 0)
                    - overlap * 1.1
                )
            return candidate['score'] - overlap * 3.25 + novelty

        best = max(pool, key=adjusted)
        selected.append(best)
        pool.remove(best)
    return selected


def get_recommendations_for_user(user, limit=20, preferences=None):
    if not user or not user.is_authenticated:
        raise ValueError('An authenticated database user is required for recommendations.')
    prefs = normalize_preferences(preferences)
    movies = list(_base_queryset(Movie))
    series = list(_base_queryset(Series))
    candidates = movies + series
    lookup = {_content_key(_content_type(item), item.id): item for item in candidates}
    profile = _build_profile(user, lookup, candidates)
    effective = _effective_preferences(profile, prefs)
    ranked = sorted(
        (_score_item(item, profile, effective) for item in candidates),
        key=lambda entry: (-entry['score'], -entry['item'].view_count, entry['item'].id),
    )
    selected = _diversify(ranked, limit)
    return {
        'personalized': profile['confidence'] >= 0.12,
        'confidence': round(profile['confidence'], 3),
        'signals_used': profile['signal_count'],
        'taste_summary': _taste_summary(profile),
        'ranked': selected,
        'movies': [entry['item'] for entry in selected if entry['content_type'] == 'movie'],
        'series': [entry['item'] for entry in selected if entry['content_type'] == 'series'],
    }
