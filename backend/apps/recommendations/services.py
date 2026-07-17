import math
import re
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Genre, Movie, Series
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem


EVENT_WINDOW_DAYS = 90
RECENCY_HALF_LIFE_DAYS = 14
CANDIDATE_POOL_SIZE = 250


def _normalize(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')).strip().lower()


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


def _base_queryset(model):
    return (
        model.objects.filter(is_published=True)
        .prefetch_related('genres', 'directors', 'countries')
        .order_by('-is_featured', '-site_rating', '-view_count', '-created_at')[:CANDIDATE_POOL_SIZE]
    )


def _load_content(keys):
    movie_ids = [object_id for content_type, object_id in keys if content_type == 'movie']
    series_ids = [object_id for content_type, object_id in keys if content_type == 'series']
    objects = {}
    if movie_ids:
        for item in Movie.objects.filter(id__in=movie_ids).prefetch_related('genres', 'directors', 'countries'):
            objects[_content_key('movie', item.id)] = item
    if series_ids:
        for item in Series.objects.filter(id__in=series_ids).prefetch_related('genres', 'directors', 'countries'):
            objects[_content_key('series', item.id)] = item
    return objects


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
            key = f'{event.action}:{event.query}:{metadata.get("genre", "")}:{metadata.get("filter_value", "")}:{event.created_at.date().isoformat()}'

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
    weights = {
        'view_movie': 0.45,
        'view_series': 0.45,
        'trailer_watch': 1.1,
        'play': 1.8,
        'pause': 0.7 if progress >= 20 else 0.2,
        'watch_progress': 0 if progress < 10 else 0.8 + progress * 0.045,
        'complete_watch': 6,
        'add_to_watchlist': 4,
        'remove_from_watchlist': -1,
        'like': 7,
        'remove_like': -0.75,
        'dislike': -10,
        'click_search_result': 1.2,
        'filter_genre': 2.5,
        'open_actor_page': 3.25,
        'open_director_page': 3.5,
    }
    if event.action == 'rate':
        return (float(event.value) - 5) * 1.6
    return weights.get(event.action, 0)


def _exact_item_weight(event):
    progress = max(0, min(100, event.progress or 0))
    weights = {
        'click_search_result': 1.5,
        'trailer_watch': 1.5,
        'play': -1,
        'watch_progress': -max(1, progress * 0.12),
        'complete_watch': -75,
        'add_to_watchlist': 9,
        'remove_from_watchlist': -14,
        'like': -4,
        'remove_like': -10,
        'dislike': -140,
    }
    if event.action == 'rate':
        return -5 if event.value >= 7 else -55 if event.value <= 4 else -12
    return weights.get(event.action, 0)


def _empty_profile():
    return {
        'genres': defaultdict(float),
        'directors': defaultdict(float),
        'countries': defaultdict(float),
        'languages': defaultdict(float),
        'formats': defaultdict(float),
        'content_types': defaultdict(float),
        'items': defaultdict(float),
        'completed': set(),
        'disliked': set(),
        'positive_items': [],
        'evidence': 0.0,
    }


def _add_content_features(profile, item, weight):
    for genre in item.genres.all():
        _add(profile['genres'], genre.slug, weight)
    for director in item.directors.all():
        _add(profile['directors'], director.name, weight * 0.75)
    for country in item.countries.all():
        _add(profile['countries'], _normalize(country.name), weight * 0.4)
    _add(profile['languages'], _normalize(item.language), weight * 0.35)
    _add(profile['formats'], item.content_format, weight * 0.5)
    _add(profile['content_types'], _content_type(item), weight * 0.55)


def _event_queryset(user, session_key):
    identity = Q()
    if user and user.is_authenticated:
        identity |= Q(user=user)
    if session_key:
        identity |= Q(session_key=session_key)
    if not identity:
        return UserActivityEvent.objects.none()
    return UserActivityEvent.objects.filter(
        identity,
        created_at__gte=timezone.now() - timedelta(days=EVENT_WINDOW_DAYS),
    ).order_by('created_at')


def _build_profile(user, session_key, catalog_lookup):
    profile = _empty_profile()
    now = timezone.now()
    events = list(_event_queryset(user, session_key))
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

    for event in _collapse_events(events):
        recency = _recency(event.created_at, now)
        weight = _event_weight(event) * recency
        profile['evidence'] += min(6, abs(weight))
        metadata = event.metadata or {}
        genre = metadata.get('genre')
        if genre:
            _add(profile['genres'], genre, weight or 2 * recency)
        if event.action == 'filter_genre':
            filter_value = metadata.get('filter_value')
            if metadata.get('filter_name') in {'genre', 'home_category'} and filter_value:
                _add(profile['genres'], str(filter_value).removeprefix('genre:'), weight)
        if event.action == 'open_director_page':
            _add(profile['directors'], metadata.get('filter_value'), weight)

        key = _content_key(event.content_type, event.object_id) if event.content_type in {'movie', 'series'} and event.object_id else None
        item = catalog_lookup.get(key) if key else None
        if item:
            _add_content_features(profile, item, weight)
            profile['items'][key] += _exact_item_weight(event) * recency
            if weight >= 1.4 and item not in profile['positive_items']:
                profile['positive_items'].append(item)
            if event.action == 'complete_watch':
                profile['completed'].add(key)
            if event.action == 'dislike' or (event.action == 'rate' and event.value <= 3):
                profile['disliked'].add(key)
            if event.action == 'like':
                profile['disliked'].discard(key)

    if user and user.is_authenticated:
        for content_type, object_id in Like.objects.filter(user=user).values_list('content_type', 'object_id'):
            key = _content_key(content_type, object_id)
            if key in catalog_lookup:
                _add_content_features(profile, catalog_lookup[key], 7)
                profile['items'][key] -= 4
                profile['positive_items'].append(catalog_lookup[key])
                profile['evidence'] += 4
        for content_type, object_id in WatchlistItem.objects.filter(user=user).values_list('content_type', 'object_id'):
            key = _content_key(content_type, object_id)
            if key in catalog_lookup:
                _add_content_features(profile, catalog_lookup[key], 4)
                profile['items'][key] += 9
                if catalog_lookup[key] not in profile['positive_items']:
                    profile['positive_items'].append(catalog_lookup[key])
                profile['evidence'] += 3
        for rating in ratings:
            key = _content_key(rating.content_type, rating.object_id)
            if key in catalog_lookup:
                weight = (float(rating.score) - 5) * 1.6
                _add_content_features(profile, catalog_lookup[key], weight)
                profile['evidence'] += min(6, abs(weight))
                if weight >= 1.4 and catalog_lookup[key] not in profile['positive_items']:
                    profile['positive_items'].append(catalog_lookup[key])
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

    profile['confidence'] = min(1, 1 - math.exp(-profile['evidence'] / 16))
    profile['signal_count'] = len(events) + len(engagement_pairs)
    return profile


def _rating(item):
    return float(item.site_rating or item.imdb_rating or 0)


def _score_item(item, profile):
    key = _content_key(_content_type(item), item.id)
    score = _rating(item) * 1.4 + math.log1p(item.view_count) * 0.65 + math.log1p(item.like_count) * 0.8
    score += 6 if item.is_featured else 0
    score += profile['items'].get(key, 0)
    behavior = _squash(profile['content_types'].get(_content_type(item), 0)) * 0.7

    best_genre = None
    best_genre_score = 0
    for genre in item.genres.all():
        genre_score = profile['genres'].get(genre.slug, 0)
        behavior += _squash(genre_score) * 1.05
        if genre_score > best_genre_score:
            best_genre = genre
            best_genre_score = genre_score
    best_director = None
    best_director_score = 0
    for director in item.directors.all():
        director_score = profile['directors'].get(director.name, 0)
        behavior += _squash(director_score) * 0.9
        if director_score > best_director_score:
            best_director = director
            best_director_score = director_score
    for country in item.countries.all():
        behavior += _squash(profile['countries'].get(_normalize(country.name), 0)) * 0.45
    behavior += _squash(profile['languages'].get(_normalize(item.language), 0)) * 0.45
    behavior += _squash(profile['formats'].get(item.content_format, 0)) * 0.65
    score += behavior * (0.45 + profile['confidence'] * 0.55)
    context_similarity = max(
        (_similarity(item, context) for context in profile['positive_items'] if context.pk != item.pk or _content_type(context) != _content_type(item)),
        default=0,
    )
    score += context_similarity * (7 + profile['confidence'] * 7)

    if key in profile['completed']:
        score -= 30
    if key in profile['disliked']:
        score -= 100

    if best_genre_score >= 1.8:
        reason = f'به‌خاطر علاقه شما به ژانر {best_genre.title}'
    elif best_director_score >= 1.8:
        reason = f'به‌خاطر علاقه شما به آثار {best_director.name}'
    elif item.is_featured:
        reason = 'انتخاب ویژه تحریریه با کیفیت بالا'
    else:
        reason = 'بر اساس کیفیت و محبوبیت در پلتفرم'
    return {'item': item, 'content_type': _content_type(item), 'score': round(score, 3), 'reason': reason}


def _similarity(first, second):
    first_genres = {genre.id for genre in first.genres.all()}
    second_genres = {genre.id for genre in second.genres.all()}
    union = first_genres | second_genres
    genre_similarity = len(first_genres & second_genres) / len(union) if union else 0
    return genre_similarity * 0.8 + (0.1 if _content_type(first) == _content_type(second) else 0) + (0.1 if first.content_format == second.content_format else 0)


def _diversify(ranked, limit):
    pool = ranked[:max(limit * 4, limit)]
    selected = []
    while pool and len(selected) < limit:
        best = max(
            pool,
            key=lambda candidate: candidate['score'] - (max((_similarity(candidate['item'], chosen['item']) for chosen in selected), default=0) * 3.25),
        )
        selected.append(best)
        pool.remove(best)
    return selected


def get_recommendations_for_user(user, limit=20, session_key=''):
    movies = list(_base_queryset(Movie))
    series = list(_base_queryset(Series))
    candidates = movies + series
    lookup = {_content_key(_content_type(item), item.id): item for item in candidates}
    profile = _build_profile(user, session_key, lookup)
    ranked = sorted((_score_item(item, profile) for item in candidates), key=lambda entry: (-entry['score'], -entry['item'].view_count, entry['item'].id))
    selected = _diversify(ranked, limit)
    return {
        'personalized': profile['confidence'] >= 0.15,
        'confidence': round(profile['confidence'], 3),
        'signals_used': profile['signal_count'],
        'ranked': selected,
        'movies': [entry['item'] for entry in selected if entry['content_type'] == 'movie'],
        'series': [entry['item'] for entry in selected if entry['content_type'] == 'series'],
    }
