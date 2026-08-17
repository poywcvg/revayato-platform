"""Discovery ranking for public catalog surfaces.

Algorithms use real platform signals already stored on Movie/Series:
engagement (views/likes), recent activity velocity, TMDB popularity,
editorial flags, freshness, ratings, artwork, and playback readiness.

«ترند» favors titles that are rising *now* (fresh + velocity + playable).
«منتخب» favors curated quality that still feels watchable today.
"""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta

from django.db.models import BooleanField, Case, Count, Q, Value, When
from django.utils import timezone


def _age_hours(item, now, *, field='updated') -> float:
    if field == 'created':
        stamp = getattr(item, 'created_at', None) or getattr(item, 'updated_at', None)
        floor = 1.0
    else:
        stamp = getattr(item, 'updated_at', None) or getattr(item, 'created_at', None)
        floor = 6.0
    if not stamp:
        return 24.0 * 30 if field == 'created' else 72.0
    return max(floor, (now - stamp).total_seconds() / 3600.0)


def _created_age_hours(item, now) -> float:
    return _age_hours(item, now, field='created')


def _rating(item) -> float:
    return float(
        getattr(item, 'imdb_rating', None)
        or getattr(item, 'tmdb_rating', None)
        or getattr(item, 'rating_average', None)
        or getattr(item, 'site_rating', None)
        or 0
    )


def _has_downloads(item) -> bool:
    flag = getattr(item, '_has_downloads_flag', None)
    if flag is not None:
        return bool(flag)
    links = getattr(item, 'download_links', None) or []
    if isinstance(links, list) and any(
        isinstance(row, dict) and (row.get('url') or row.get('key'))
        for row in links
    ):
        return True
    return bool(getattr(item, 'download_key', None))


def _has_artwork(item) -> bool:
    return bool(
        getattr(item, 'poster', None)
        or getattr(item, 'poster_external_url', None)
        or getattr(item, 'poster_path', None)
        or getattr(item, 'backdrop', None)
        or getattr(item, 'backdrop_external_url', None)
        or getattr(item, 'backdrop_path', None)
    )


def _playable_bonus(item) -> float:
    score = 0.0
    if getattr(item, 'is_dubbed', False):
        score += 3.5
    if getattr(item, 'has_subtitle', False):
        score += 3.0
    if _has_downloads(item):
        score += 4.0
    tracks_flag = getattr(item, '_has_subtitle_tracks_flag', None)
    if tracks_flag is not None:
        has_tracks = bool(tracks_flag)
    else:
        tracks = getattr(item, 'subtitle_tracks', None) or []
        has_tracks = bool(tracks)
    if has_tracks:
        score += 2.0
    return score


def _imdb_rank_bonus(item) -> float:
    rank = getattr(item, 'imdb_rank', None)
    try:
        rank = int(rank) if rank is not None else 0
    except (TypeError, ValueError):
        return 0.0
    if rank <= 0:
        return 0.0
    # Top 250 charts — stronger for curated «منتخب».
    if rank <= 50:
        return 6.0
    if rank <= 100:
        return 4.0
    if rank <= 250:
        return 2.5
    return 0.0


def _engagement_velocity(item, now) -> float:
    """Approximate rising interest from lifetime counts vs age."""
    created_hours = _created_age_hours(item, now)
    created_days = max(0.35, created_hours / 24.0)
    views = int(getattr(item, 'view_count', 0) or 0)
    likes = int(getattr(item, 'like_count', 0) or 0)
    views_per_day = views / created_days
    likes_per_day = likes / created_days
    # New titles with any traction should jump; old titles need sustained rate.
    freshness_gate = 1.35 if created_hours <= 24 * 10 else 1.0
    return (math.log1p(views_per_day) * 3.2 + math.log1p(likes_per_day) * 4.4) * freshness_gate


def _daily_jitter(item, *, now, salt: str, amplitude: float = 1.8) -> float:
    """Stable within a UTC day so rails refresh daily without flickering hourly."""
    day = now.strftime('%Y-%m-%d')
    pk = getattr(item, 'pk', None) or getattr(item, 'id', 0) or 0
    digest = hashlib.sha1(f'{salt}:{day}:{pk}'.encode()).hexdigest()
    unit = int(digest[:8], 16) / 0xFFFFFFFF
    return (unit - 0.5) * 2.0 * amplitude


def _slot_jitter(item, *, now, salt: str, amplitude: float = 2.4, hours: int = 6) -> float:
    """Rotate rails a few times per day (stable inside each time slot)."""
    slot_hours = max(1, int(hours))
    slot = int(now.hour // slot_hours)
    day = now.strftime('%Y-%m-%d')
    pk = getattr(item, 'pk', None) or getattr(item, 'id', 0) or 0
    digest = hashlib.sha1(f'{salt}:{day}:s{slot}:{pk}'.encode()).hexdigest()
    unit = int(digest[:8], 16) / 0xFFFFFFFF
    return (unit - 0.5) * 2.0 * amplitude


def rail_rotation_meta(now=None) -> dict:
    """Public meta so clients know which discovery slot is active."""
    now = now or timezone.now()
    bucket = int(now.hour // 6)
    day = now.strftime('%Y-%m-%d')
    focus_genres = (
        'action', 'drama', 'comedy', 'thriller', 'sci-fi', 'romance',
        'horror', 'animation', 'crime', 'adventure', 'fantasy', 'mystery',
    )
    digest = hashlib.sha1(f'focus:{day}:{bucket}'.encode()).hexdigest()
    focus = focus_genres[int(digest[:8], 16) % len(focus_genres)]
    return {
        'day': day,
        'bucket': bucket,
        'slot_hours': 6,
        'focus_genre': focus,
    }


def _genre_slugs(item) -> list[str]:
    try:
        genres = item.genres.all()
    except Exception:
        genres = getattr(item, '_prefetched_objects_cache', {}).get('genres') or []
    slugs = []
    for genre in genres:
        slug = str(getattr(genre, 'slug', '') or '').strip().lower()
        if slug:
            slugs.append(slug)
    return slugs


# Only genre diversity needs M2M data, and only on the *chosen* rows. Fetching
# genres/directors/countries for the whole ~520-row candidate pool was costing
# extra prefetch queries per rail. Fetch them once for the small ordered slice
# the rail actually returns.
_DIVERSITY_PREFETCH = ('genres', 'directors', 'countries')


def _prefetch_candidates(candidates, *relations) -> list:
    """Prefetch M2M relations on already-fetched model rows (one query per
    relation instead of one per row). Used on the ordered slice a rail returns
    so discovery never fetches these for the whole candidate pool.

    Only refetches when the rows are real model instances with ``pk``s and a
    manager — the unit tests exercise ``diversify_ranked`` with plain fakes
    that carry a pre-set ``genres`` relation, which must be left untouched.
    """
    relations = relations or _DIVERSITY_PREFETCH
    if not candidates or not relations:
        return candidates
    if not all(
        hasattr(c, 'pk') and hasattr(c, '_meta') and hasattr(c, '_prefetched_objects_cache')
        for c in candidates
    ):
        return candidates
    model = candidates[0].__class__
    pks = [c.pk for c in candidates]
    objs = model.objects.filter(pk__in=pks).prefetch_related(*relations)
    by_pk = {obj.pk: obj for obj in objs}
    return [by_pk.get(c.pk) or c for c in candidates]


def diversify_ranked(ranked: list, *, limit: int, max_per_genre: int = 2) -> list:
    """Keep score order but avoid a rail dominated by one genre.

    Relations are prefetched once for the ``ranked`` slice (which the caller
    already restricted to the pages it will return) before genre diversity runs.
    """
    limit = max(1, int(limit))
    max_per_genre = max(1, int(max_per_genre))
    ranked = _prefetch_candidates(ranked)
    picked: list = []
    genre_counts: dict[str, int] = {}
    deferred: list = []

    def try_add(item, *, enforce: bool) -> bool:
        slugs = _genre_slugs(item) or ['__none__']
        primary = slugs[0]
        if enforce and genre_counts.get(primary, 0) >= max_per_genre:
            return False
        picked.append(item)
        genre_counts[primary] = genre_counts.get(primary, 0) + 1
        return True

    for item in ranked:
        if len(picked) >= limit:
            return picked
        if not try_add(item, enforce=True):
            deferred.append(item)

    # Second pass: still respect the cap when alternate genres remain.
    for item in deferred:
        if len(picked) >= limit:
            break
        try_add(item, enforce=True)

    # Last resort fill so short catalogs still return a full rail.
    if len(picked) < limit:
        chosen = {id(x) for x in picked}
        for item in ranked:
            if len(picked) >= limit:
                break
            if id(item) in chosen:
                continue
            picked.append(item)
            chosen.add(id(item))
    return picked


def recent_engagement_map(model, *, hours: int = 48) -> dict[int, float]:
    """Count consented activity hits per title in the recent window."""
    try:
        from apps.engagement.models import UserActivityEvent
    except Exception:
        return {}

    content_type = 'movie' if model.__name__ == 'Movie' else 'series'
    since = timezone.now() - timedelta(hours=max(6, int(hours)))
    rows = (
        UserActivityEvent.objects.filter(
            content_type=content_type,
            object_id__isnull=False,
            created_at__gte=since,
        )
        .filter(
            Q(action__in={
                'view_movie', 'view_series', 'play', 'watch_progress',
                'complete_watch', 'like', 'add_to_watchlist',
                'click_search_result', 'trailer_watch',
            })
            | Q(metadata__event_type__in={
                'view_movie', 'view_series', 'start_watch', 'continue_watch',
                'watch_progress', 'complete_watch', 'like', 'add_watchlist',
                'recommendation_click', 'play_trailer',
            })
        )
        .values('object_id')
        .annotate(hits=Count('id'))
    )
    return {
        int(row['object_id']): float(row['hits'])
        for row in rows
        if row.get('object_id')
    }


def trending_score(item, *, now=None, recent_hits: float = 0.0) -> float:
    """Higher = more relevant for «ترند امروز» — rising right now."""
    now = now or timezone.now()
    views = int(getattr(item, 'view_count', 0) or 0)
    likes = int(getattr(item, 'like_count', 0) or 0)
    popularity = float(getattr(item, 'popularity', 0) or 0)
    created_hours = _created_age_hours(item, now)
    updated_hours = _age_hours(item, now, field='updated')

    score = (
        _engagement_velocity(item, now) * 1.15
        + math.log1p(views) * 1.15
        + math.log1p(likes) * 1.55
        + popularity / 28.0
        + math.log1p(recent_hits) * 5.5
    )

    # Fresh arrivals bubble hard for the first two weeks.
    if created_hours <= 24:
        score += 10.0
    elif created_hours <= 24 * 3:
        score += 7.0
    elif created_hours <= 24 * 7:
        score += 4.5
    elif created_hours <= 24 * 14:
        score += 2.2
    else:
        score += 6.0 / math.sqrt(created_hours / 24.0)

    # Light touch for recently touched rows, but don't let metadata edits fake a trend.
    if updated_hours <= 36 and created_hours > 48:
        score += 1.2

    score += _playable_bonus(item) * 1.05
    if _has_artwork(item):
        score += 1.6

    # Editorial flags are a nudge on trending — not the main driver.
    if getattr(item, 'is_featured', False):
        score += 2.4
    if getattr(item, 'is_recommended', False):
        score += 1.6

    rating = _rating(item)
    if rating:
        score += max(0.0, (rating - 6.0) * 0.55)

    # Stale lifetime-popular titles sink unless they keep getting hits.
    if created_hours > 24 * 21 and recent_hits < 2:
        score *= 0.82
    if created_hours > 24 * 45 and recent_hits < 1:
        score *= 0.88

    score += _daily_jitter(item, now=now, salt='trending', amplitude=2.2)
    return score


def featured_score(item, *, now=None, recent_hits: float = 0.0) -> float:
    """Higher = better for «منتخب‌ها» — curated quality that still feels alive."""
    now = now or timezone.now()
    popularity = float(getattr(item, 'popularity', 0) or 0)
    views = int(getattr(item, 'view_count', 0) or 0)
    likes = int(getattr(item, 'like_count', 0) or 0)
    rating = _rating(item)
    created_age = _created_age_hours(item, now)

    score = (
        popularity / 16.0
        + math.log1p(views) * 0.85
        + math.log1p(likes) * 1.35
        + max(0.0, (rating - 5.5) * 2.8)
        + _imdb_rank_bonus(item)
        + math.log1p(recent_hits) * 2.2
    )
    score += _playable_bonus(item) * 1.05
    if _has_artwork(item):
        score += 2.4

    if getattr(item, 'is_recommended', False):
        score += 11.0
    if getattr(item, 'is_featured', False):
        score += 9.0

    # Keep classics eligible, but refresh the shelf with recent curated picks.
    score += 7.0 / math.sqrt(max(1.0, created_age / 24.0))
    if created_age <= 24 * 21:
        score += 2.8

    # Slot rotation among near-ties so «منتخب» reshuffles a few times per day.
    score += _slot_jitter(item, now=now, salt='featured', amplitude=2.6)
    return score


def popular_score(item, *, now=None, recent_hits: float = 0.0) -> float:
    """Higher = better for «محبوب» — sustained audience signal."""
    now = now or timezone.now()
    views = int(getattr(item, 'view_count', 0) or 0)
    likes = int(getattr(item, 'like_count', 0) or 0)
    popularity = float(getattr(item, 'popularity', 0) or 0)
    rating = _rating(item)
    age_hours = _age_hours(item, now, field='updated')
    created_hours = _created_age_hours(item, now)

    score = (
        math.log1p(views) * 3.4
        + math.log1p(likes) * 4.2
        + popularity / 12.0
        + max(0.0, (rating - 6.0) * 1.1)
        + math.log1p(recent_hits) * 2.4
        + _engagement_velocity(item, now) * 0.55
    )
    score += _playable_bonus(item) * 0.55

    if getattr(item, 'is_featured', False):
        score += 2.0
    if getattr(item, 'is_recommended', False):
        score += 1.5

    # Fresh titles with growing traction still surface in «محبوب».
    if created_hours <= 24 * 14:
        score += 2.2

    if age_hours > 24 * 45:
        score *= 0.9

    score += _slot_jitter(item, now=now, salt='popular', amplitude=2.0)
    return score


def dubbed_score(item, *, now=None, recent_hits: float = 0.0) -> float:
    """Home «دوبله فارسی» — only dubbed titles; live demand + mild rotation."""
    now = now or timezone.now()
    # Hard gate: never promote non-dubbed rows even if they sneak into the pool.
    if not getattr(item, 'is_dubbed', False):
        return -1e9

    views = int(getattr(item, 'view_count', 0) or 0)
    likes = int(getattr(item, 'like_count', 0) or 0)
    popularity = float(getattr(item, 'popularity', 0) or 0)
    rating = _rating(item)
    created_hours = _created_age_hours(item, now)

    score = (
        math.log1p(views) * 1.6
        + math.log1p(likes) * 2.1
        + popularity / 18.0
        + max(0.0, (rating - 5.8) * 1.4)
        + math.log1p(recent_hits) * 3.2
        + _engagement_velocity(item, now) * 0.8
    )

    if getattr(item, 'has_subtitle', False):
        score += 1.6
    score += _playable_bonus(item) * 0.85
    if _has_artwork(item):
        score += 1.8

    if created_hours <= 24 * 7:
        score += 4.5
    elif created_hours <= 24 * 30:
        score += 2.0

    if getattr(item, 'is_featured', False):
        score += 1.8
    if getattr(item, 'is_recommended', False):
        score += 1.2

    score += _slot_jitter(item, now=now, salt='dubbed', amplitude=2.4)
    return score


def newest_timestamp(item) -> float:
    """Unix timestamp for «تازه اضافه شده‌ها» — prefer first publish time."""
    stamp = getattr(item, 'created_at', None) or getattr(item, 'updated_at', None)
    if not stamp:
        return 0.0
    return stamp.timestamp()


SCORE_FNS = {
    'trending': trending_score,
    'featured': featured_score,
    'popular': popular_score,
    'dubbed': dubbed_score,
}


# Public cards and ranking never read these fields. Deferring them keeps wide
# metadata/SEO JSON and full synopses out of candidate queries (which may scan
# hundreds of rows) without changing model, serializer, or response contracts.
# download_links / subtitle_tracks are the heaviest JSONB blobs; ranking only
# needs a boolean, computed server-side by _ranked_annotations().
_RANKING_DEFER_FIELDS = {
    'Movie': (
        'description', 'release_date', 'catalog_type', 'publication_status',
        'video_url', 'media_status', 'rights_verified', 'auto_publish',
        'scheduled_publish_at', 'metadata_source', 'metadata_synced_at',
        'source_metadata', 'manual_override_fields', 'quality',
        'spoken_languages', 'production_companies', 'crew_metadata', 'writers',
        'original_language', 'content_warnings', 'meta_title',
        'meta_description', 'seo_keywords',
        'download_links', 'subtitle_tracks',
    ),
    'Series': (
        'description', 'content_warnings', 'original_language',
        'metadata_source', 'metadata_synced_at', 'source_metadata',
        'download_links',
    ),
}


def _ranked_annotations(model):
    """SQL-computed booleans replacing the decoded download_links/subtitle_tracks
    JSONB blobs on ranked candidates (movie series can carry megabytes per row).

    Named with a leading underscore so Django can set them without colliding
    with the read-only ``has_downloads`` property.
    """
    model_fields = {field.name for field in model._meta.get_fields()}
    conditions = []
    if 'download_key' in model_fields:
        conditions.append(When(download_key__gt='', then=Value(True)))
    conditions += [
        When(download_links=Value([]), then=Value(False)),
        When(download_links__isnull=True, then=Value(False)),
    ]
    annotations = {
        '_has_downloads_flag': Case(
            *conditions,
            default=Value(True),
            output_field=BooleanField(),
        ),
    }
    if 'subtitle_tracks' in model_fields:
        annotations['_has_subtitle_tracks_flag'] = Case(
            When(subtitle_tracks=Value([]), then=Value(False)),
            When(subtitle_tracks__isnull=True, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        )
    return annotations


def lean_public_queryset(queryset, *, keep=()):
    """Defer fields unused by public list serializers and discovery scoring.

    ``keep`` lets a caller retain a normally deferred field when its own scorer
    needs it (recommendations, for example, inspect ``content_warnings``).
    """
    retained = set(keep or ())
    fields = tuple(
        field
        for field in _RANKING_DEFER_FIELDS.get(queryset.model.__name__, ())
        if field not in retained
    )
    return queryset.defer(*fields) if fields else queryset


def _candidate_pool(queryset, *, sort: str, pool: int):
    """Mix fresh + engaged + editorial candidates so rising titles are not missed."""
    base = lean_public_queryset(queryset)
    annotations = _ranked_annotations(base.model)
    if sort == 'popular':
        # The primary ordering already yields a full unique pool. A separate
        # ID merge + hydration pass only adds a round-trip for this common path.
        return list(base.order_by('-view_count', '-like_count', '-popularity').annotate(**annotations)[:pool])

    model_fields = {field.name for field in base.model._meta.get_fields()}
    editorial_filter = Q(is_featured=True)
    if 'is_recommended' in model_fields:
        editorial_filter |= Q(is_recommended=True)
    slices = []
    if sort == 'trending':
        slices = [
            base.order_by('-created_at')[: max(40, pool // 3)],
            base.order_by('-view_count', '-like_count', '-updated_at')[: max(40, pool // 2)],
            base.filter(editorial_filter)
            .order_by('-updated_at')[: max(24, pool // 4)],
            base.filter(Q(is_dubbed=True) | Q(has_subtitle=True))
            .order_by('-created_at')[: max(24, pool // 4)],
        ]
    elif sort == 'featured':
        slices = [
            base.filter(editorial_filter)
            .order_by('-popularity', '-view_count')[: max(60, pool // 2)],
            base.order_by('-popularity', '-like_count', '-view_count')[: max(40, pool // 2)],
            base.filter(imdb_rank__isnull=False).order_by('imdb_rank')[:80],
            base.order_by('-created_at')[:40],
        ]
    elif sort == 'dubbed':
        slices = [
            base.filter(is_dubbed=True).order_by('-created_at')[: max(60, pool // 2)],
            base.filter(is_dubbed=True).order_by('-view_count', '-like_count')[: max(60, pool // 2)],
            base.filter(is_dubbed=True, has_subtitle=True).order_by('-popularity')[:40],
            base.filter(is_dubbed=True).filter(editorial_filter)[:30],
        ]
    else:
        raise ValueError(f'Unsupported candidate sort: {sort}')

    # First merge only primary keys. Evaluating every slice as model instances
    # would run its prefetches repeatedly and transfer wide rows that are later
    # discarded as duplicates. Hydrate the final unique pool exactly once.
    merged_ids = {}
    for chunk in slices:
        for item_id in chunk.values_list('pk', flat=True):
            merged_ids[item_id] = None
            if len(merged_ids) >= pool:
                return list(base.filter(pk__in=merged_ids).order_by().annotate(**annotations))
    # Fallback fill if filters were sparse.
    if len(merged_ids) < min(pool, 48):
        fallback = base.order_by('-popularity', '-view_count', '-updated_at')[:pool]
        for item_id in fallback.values_list('pk', flat=True):
            merged_ids[item_id] = None
    if not merged_ids:
        return []
    return list(base.filter(pk__in=merged_ids).order_by().annotate(**annotations))


def rank_queryset(queryset, *, sort: str, limit: int = 20, offset: int = 0, pool_size: int | None = None):
    """Score a filtered queryset in Python and return a page of models."""
    score_fn = SCORE_FNS.get(sort)
    if score_fn is None:
        raise ValueError(f'Unsupported scored sort: {sort}')

    limit = max(1, int(limit))
    offset = max(0, int(offset))
    pool = pool_size or min(max((limit + offset) * 5, 120), 520)

    model = queryset.model
    candidates = _candidate_pool(queryset, sort=sort, pool=pool)
    now = timezone.now()
    recent = recent_engagement_map(model, hours=48) if sort in {'trending', 'featured'} else {}
    ranked = sorted(
        candidates,
        key=lambda item: score_fn(item, now=now, recent_hits=recent.get(item.pk, 0.0)),
        reverse=True,
    )
    page = ranked[offset:offset + limit]
    # Series lists carry tags; discovery lists carry genres/directors/countries.
    extra = ('tags',) if model.__name__ == 'Series' else ()
    page = _prefetch_candidates(page, *_DIVERSITY_PREFETCH, *extra)
    return page, len(ranked)


def trending_queryset(model, *, limit: int = 20):
    """Return published titles ordered for «ترند امروز»."""
    page, _total = rank_queryset(
        lean_public_queryset(model.objects.filter(is_published=True)),
        sort='trending',
        limit=limit,
        offset=0,
    )
    return page


def featured_queryset(model, *, limit: int = 20):
    """Return published titles ordered for «منتخب‌ها»."""
    page, _total = rank_queryset(
        lean_public_queryset(model.objects.filter(is_published=True)),
        sort='featured',
        limit=limit,
        offset=0,
    )
    return page


def _rank_with_diversity(queryset, *, sort: str, limit: int, score_kwargs: dict | None = None):
    score_fn = SCORE_FNS.get(sort)
    if score_fn is None:
        raise ValueError(f'Unsupported scored sort: {sort}')
    limit = max(1, int(limit))
    pool = min(max(limit * 8, 140), 520)
    candidates = _candidate_pool(queryset, sort=sort, pool=pool)
    now = timezone.now()
    recent = recent_engagement_map(queryset.model, hours=48)
    kwargs = score_kwargs or {}
    ranked = sorted(
        candidates,
        key=lambda item: score_fn(
            item,
            now=now,
            recent_hits=recent.get(item.pk, 0.0),
            **kwargs,
        ),
        reverse=True,
    )
    return diversify_ranked(ranked, limit=limit, max_per_genre=2)


def build_home_rails(*, limit: int = 7) -> dict:
    """Assemble home discovery rails with live scores + slot rotation."""
    from apps.catalog.models import Movie, Series

    limit = max(1, min(int(limit), 24))
    now = timezone.now()
    meta = rail_rotation_meta(now)

    movie_base = lean_public_queryset(Movie.objects.filter(is_published=True))
    series_base = lean_public_queryset(Series.objects.filter(is_published=True))

    featured = _rank_with_diversity(movie_base, sort='featured', limit=limit)
    dubbed = _rank_with_diversity(
        movie_base.filter(is_dubbed=True),
        sort='dubbed',
        limit=limit,
    )
    # Absolute safety: never leak a non-dubbed title into this rail.
    dubbed = [item for item in dubbed if getattr(item, 'is_dubbed', False)]
    popular_series = _rank_with_diversity(series_base, sort='popular', limit=limit)

    return {
        'meta': {
            **meta,
            'limit': limit,
            'eyebrow': {
                'featured': 'انتخاب‌های تازه این بازه',
                'dubbed': 'فقط نسخه دوبله فارسی',
                'popular_series': 'بر اساس بازدید، پسند و تازگی',
            },
        },
        'featured': featured,
        'dubbed': dubbed,
        'popular_series': popular_series,
    }
