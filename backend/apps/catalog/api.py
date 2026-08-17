from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Prefetch, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .cache import (
    build_catalog_cache_key,
    cache_control_for,
    catalog_cache_ttl,
    get_cached_payload,
    set_cached_payload,
)
from .countries import country_code_for_name
from .models import (
    Actor, Country, Director, Episode, Genre, Movie, MovieActor, Season, Series,
    SeriesActor,
)
from .search import (
    normalize_search_text,
    normalize_search_digits,
    parse_search_query,
    rank_similar_title_ids,
    search_query_variants,
    title_rank_annotation,
    title_search_q,
)
from .serializers import (
    ActorDetailSerializer, ActorListSerializer, CountrySerializer, DirectorListSerializer,
    GenreListSerializer, GenreSerializer, MovieDetailSerializer, MovieListSerializer,
    SeriesDetailSerializer, SeriesListSerializer,
)


class CatalogReadThrottle(AnonRateThrottle):
    scope = 'catalog'


class PlaybackSubtitleEnsureThrottle(AnonRateThrottle):
    """Allow a few urgent SoftSub ensures per client without starving catalog reads."""

    scope = 'playback_subtitle_ensure'


def _queue_missing_softsub(obj, *, kind: str) -> None:
    """Best-effort SoftSub / SubtitleStar backfill when a public detail page is viewed."""
    try:
        from django.conf import settings
        from apps.catalog.subtitle_extract import (
            download_links_imply_softsub,
            normalize_imdb_id_safe,
        )
        from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub

        links = [item for item in (getattr(obj, 'download_links', None) or []) if isinstance(item, dict)]
        if kind == 'movie':
            if getattr(obj, 'subtitle_tracks', None):
                return
            eligible = download_links_imply_softsub(links) or (
                bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True))
                and bool(normalize_imdb_id_safe(obj) or getattr(obj, 'imdb_id', None))
                and bool(links)
            )
            if eligible:
                enqueue_movie_softsub(obj.pk, force=False)
            return

        if kind == 'series':
            from django.db.models import Q
            from apps.catalog.models import Episode

            # Keep queueing while any published episode still lacks SoftSub tracks.
            missing_tracks = Episode.objects.filter(
                season__series_id=obj.pk,
                is_published=True,
            ).filter(Q(subtitle_tracks=[]) | Q(subtitle_tracks__isnull=True)).exists()
            if not missing_tracks:
                return
            eligible = download_links_imply_softsub(links) or (
                bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True))
                and bool(
                    normalize_imdb_id_safe(obj)
                    or (
                        str(getattr(obj, 'original_title', '') or getattr(obj, 'title', '') or '').strip()
                        and getattr(obj, 'start_year', None)
                    )
                )
                and bool(links)
            )
            if eligible:
                enqueue_series_softsub(obj.pk, force=False, episode_limit=40)
    except Exception:
        # Detail responses must never fail because SoftSub queueing failed.
        import logging
        logging.getLogger(__name__).exception('softsub queue on detail failed for %s %s', kind, getattr(obj, 'pk', None))


def _cached_response(request, namespace: str, kind: str, builder):
    """Serve anonymous catalog JSON from Redis when available."""
    ttl = catalog_cache_ttl(kind)
    cache_key = build_catalog_cache_key(namespace, request) if ttl > 0 else None
    if cache_key:
        cached = get_cached_payload(cache_key)
        if cached is not None:
            response = Response(cached)
            response['Cache-Control'] = cache_control_for(kind)
            response['X-Catalog-Cache'] = 'HIT'
            return response

    payload = builder()
    if cache_key:
        set_cached_payload(cache_key, payload, ttl)
    response = Response(payload)
    response['Cache-Control'] = cache_control_for(kind)
    response['X-Catalog-Cache'] = 'MISS'
    return response


def _relative_pagination_link(url):
    """Keep path+query only so Redis-cached pages work for SSR and browsers."""
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit(('', '', parts.path, parts.query, '')) or None


def _paginated_cached_response(request, namespace: str, queryset, serializer_class, kind='list'):
    ttl = catalog_cache_ttl(kind)
    cache_key = build_catalog_cache_key(namespace, request) if ttl > 0 else None
    if cache_key:
        cached = get_cached_payload(cache_key)
        if cached is not None:
            response = Response(cached)
            response['Cache-Control'] = cache_control_for(kind)
            response['X-Catalog-Cache'] = 'HIT'
            return response

    paginator = LimitOffsetPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        payload = {
            'count': paginator.count,
            'next': _relative_pagination_link(paginator.get_next_link()),
            'previous': _relative_pagination_link(paginator.get_previous_link()),
            'results': serializer_class(page, many=True).data,
        }
    else:
        payload = serializer_class(queryset, many=True).data

    if cache_key:
        set_cached_payload(cache_key, payload, ttl)
    response = Response(payload)
    response['Cache-Control'] = cache_control_for(kind)
    response['X-Catalog-Cache'] = 'MISS'
    return response


def _bounded_int(value, default, minimum=0, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _text_search_q(variants, *fields):
    query = Q()
    for variant in variants:
        for field in fields:
            query |= Q(**{f'{field}__icontains': variant})
    return query


def _resolve_related_search_ids(variants, *, include_genres=False):
    """Resolve person/genre text once, before joining it back to catalog rows."""
    related_limit = 160
    actor_ids = list(
        Actor.objects
        .filter(_text_search_q(variants, 'name', 'original_name'))
        .order_by('-popularity', 'id')
        .values_list('id', flat=True)[:related_limit]
    )
    director_ids = list(
        Director.objects
        .filter(_text_search_q(variants, 'name', 'original_name'))
        .order_by('-popularity', 'id')
        .values_list('id', flat=True)[:related_limit]
    )
    genre_ids = []
    if include_genres:
        genre_ids = list(
            Genre.objects
            .filter(_text_search_q(variants, 'title', 'slug'))
            .order_by('-is_featured', 'id')
            .values_list('id', flat=True)[:40]
        )
    return {
        'actor_ids': actor_ids,
        'director_ids': director_ids,
        'genre_ids': genre_ids,
    }


def _related_catalog_search_q(
    model,
    variants=(),
    *,
    include_genres=False,
    resolved=None,
):
    """Return catalog relation matches as indexed ID subqueries.

    The previous correlated EXISTS query searched actor/director text once for
    every catalog row.  A miss therefore multiplied a 64k-person scan by roughly
    16k movies and regularly hit PostgreSQL's five-second statement timeout.
    Resolve a bounded set of matching people once, then follow the indexed
    through-table foreign keys back to movie/series IDs.  No wide DISTINCT count
    or per-row person scan is needed.
    """
    if model is Movie:
        actor_links = MovieActor.objects
        owner_key = 'movie_id'
    elif model is Series:
        actor_links = SeriesActor.objects
        owner_key = 'series_id'
    else:
        return Q(pk__in=[])

    resolved = resolved or _resolve_related_search_ids(
        variants,
        include_genres=include_genres,
    )
    actor_ids = resolved['actor_ids']
    director_ids = resolved['director_ids']
    actor_owner_ids = actor_links.filter(actor_id__in=actor_ids).values(owner_key)
    director_owner_ids = (
        model.directors.through.objects
        .filter(director_id__in=director_ids)
        .values(owner_key)
    )
    relation_q = Q(pk__in=actor_owner_ids) | Q(pk__in=director_owner_ids)

    if include_genres:
        genre_ids = resolved['genre_ids']
        genre_owner_ids = (
            model.genres.through.objects
            .filter(genre_id__in=genre_ids)
            .values(owner_key)
        )
        relation_q |= Q(pk__in=genre_owner_ids)

    return relation_q


def _apply_catalog_filters(queryset, request, year_field):
    query = request.GET.get('q', '').strip()
    year = _bounded_int(normalize_search_digits(request.GET.get('year')), None, 1888, 2100)
    genre = request.GET.get('genre', '').strip()
    country = request.GET.get('country', '').strip()
    language = request.GET.get('language', '').strip()
    age_rating = request.GET.get('age_rating', request.GET.get('age', '')).strip()
    availability = request.GET.get('availability', '').strip()
    content_format = request.GET.get('content_format', '').strip()
    min_rating = _decimal(request.GET.get('min_rating'))
    tag = request.GET.get('tag', '').strip()

    # The header has one input, so understand both "2024" and "Dune 2021"
    # even when a client has not split the year into its own query parameter.
    if query and year is None:
        parsed_query = parse_search_query(query)
        query = parsed_query.text
        year = parsed_query.year

    if query:
        variants = search_query_variants(query)
        title_match = _text_search_q(variants, 'title', 'original_title', 'slug')
        title_queryset = queryset.filter(title_match)
        # A title hit is the clearest interpretation and is fully covered by
        # the pg_trgm indexes. Only expand to cast/directors when titles miss;
        # this avoids an expensive OR plan in paginated COUNT queries.
        if title_queryset.only('pk').exists():
            queryset = title_queryset
        else:
            queryset = queryset.filter(
                _related_catalog_search_q(queryset.model, variants)
            )
    if year is not None:
        queryset = queryset.filter(**{year_field: year})
    if genre:
        queryset = queryset.filter(genres__slug=genre)
    if tag:
        queryset = queryset.filter(tags__slug=tag)
    if country:
        country_code = country_code_for_name(country)
        queryset = queryset.filter(
            Q(countries__code__iexact=country_code) | Q(countries__name__iexact=country)
        )
    if language:
        queryset = queryset.filter(language__icontains=language)
    if age_rating:
        queryset = queryset.filter(age_rating=age_rating)
    if availability == 'dubbed':
        queryset = queryset.filter(is_dubbed=True)
    elif availability == 'subtitle':
        queryset = queryset.filter(has_subtitle=True)
    elif availability == 'download':
        availability_q = Q()
        if hasattr(queryset.model, 'download_links'):
            availability_q |= (
                Q(download_links__isnull=False) & ~Q(download_links=[])
            )
        if hasattr(queryset.model, 'download_key'):
            availability_q |= Q(download_key__isnull=False) & ~Q(download_key='')
        queryset = queryset.filter(availability_q)
    if content_format in {'live_action', 'animation', 'short'}:
        queryset = queryset.filter(content_format=content_format)
    if min_rating is not None:
        queryset = queryset.filter(imdb_rating__gte=min_rating)
    if str(request.GET.get('top250') or '').strip().lower() in {'1', 'true', 'yes'}:
        queryset = queryset.exclude(imdb_rank__isnull=True)

    # Genre/tag/country slugs or codes are unique, while people search uses
    # EXISTS above, so the base queryset remains one row per catalog title.
    return queryset


def _catalog_ordering(request, year_field):
    sort = request.GET.get('sort', 'newest')
    if sort in {'imdb_top', 'imdb_rank', 'top250'}:
        return [F('imdb_rank').asc(nulls_last=True), F('imdb_rating').desc(nulls_last=True), '-view_count']
    if sort == 'rating':
        return [F('imdb_rating').desc(nulls_last=True), F('site_rating').desc(nulls_last=True), '-view_count']
    if sort == 'trending':
        # Coarse SQL pre-order; list endpoints re-score with trending.py for accuracy.
        return ['-is_featured', '-view_count', '-like_count', '-popularity', '-updated_at']
    if sort == 'featured':
        return ['-is_featured', '-popularity', '-view_count', '-like_count', '-updated_at']
    if sort == 'popular':
        return ['-view_count', '-like_count', '-popularity', '-created_at']
    if sort == 'year':
        return [F(year_field).desc(nulls_last=True), '-created_at']
    # newest: truly newly added titles first (not metadata-touched updated_at).
    return ['-created_at', '-id']


def _uses_scored_sort(request) -> str | None:
    sort = request.GET.get('sort', 'newest')
    if sort in {'trending', 'featured', 'popular'}:
        return sort
    return None


def _scored_paginated_response(request, namespace: str, queryset, serializer_class, sort: str, kind='list'):
    """Paginate after Python ranking so discovery sorts match home rails."""
    from apps.catalog.trending import rank_queryset

    ttl = catalog_cache_ttl(kind)
    cache_key = build_catalog_cache_key(namespace, request) if ttl > 0 else None
    if cache_key:
        cached = get_cached_payload(cache_key)
        if cached is not None:
            response = Response(cached)
            response['Cache-Control'] = cache_control_for(kind)
            response['X-Catalog-Cache'] = 'HIT'
            return response

    limit = _bounded_int(request.GET.get('limit'), 20, 1, 120)
    offset = _bounded_int(request.GET.get('offset'), 0, 0, 10_000)
    page, scored_total = rank_queryset(
        queryset,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    # Count reflects scored candidate pool so clients don't invent phantom pages.
    count = max(scored_total, offset + len(page))
    next_offset = offset + limit
    previous_offset = offset - limit
    base = request.path
    query = request.GET.copy()
    payload = {
        'count': count,
        'next': None,
        'previous': None,
        'results': serializer_class(page, many=True).data,
    }
    if next_offset < count:
        query['limit'] = str(limit)
        query['offset'] = str(next_offset)
        payload['next'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
    if previous_offset >= 0:
        query['limit'] = str(limit)
        query['offset'] = str(previous_offset)
        payload['previous'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
    elif offset > 0:
        query['limit'] = str(limit)
        query['offset'] = '0'
        payload['previous'] = _relative_pagination_link(f'{base}?{query.urlencode()}')

    if cache_key:
        set_cached_payload(cache_key, payload, ttl)
    response = Response(payload)
    response['Cache-Control'] = cache_control_for(kind)
    response['X-Catalog-Cache'] = 'MISS'
    return response


def _catalog_list_response(request, namespace: str, queryset, serializer_class, year_field: str):
    from apps.catalog.trending import lean_public_queryset

    queryset = lean_public_queryset(queryset)
    scored = _uses_scored_sort(request)
    if scored:
        return _scored_paginated_response(request, namespace, queryset, serializer_class, scored)
    return _paginated_cached_response(
        request,
        namespace,
        queryset.order_by(*_catalog_ordering(request, year_field)),
        serializer_class,
    )


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def movie_list(request):
    queryset = _apply_catalog_filters(
        Movie.objects.filter(is_published=True), request, 'release_year',
    ).prefetch_related('genres', 'directors', 'countries')
    return _catalog_list_response(request, 'movies', queryset, MovieListSerializer, 'release_year')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def movie_detail(request, slug):
    def build():
        movie = get_object_or_404(
            Movie.objects.filter(is_published=True)
            .prefetch_related('genres', 'movie_actors__actor', 'directors', 'countries', 'tags'),
            slug=slug,
        )
        return MovieDetailSerializer(movie).data

    # Queue even on cache hits so SoftSub / SubtitleStar backfill still runs.
    movie = Movie.objects.filter(is_published=True, slug=slug).only(
        'id', 'imdb_id', 'download_links', 'subtitle_tracks', 'title', 'original_title',
    ).first()
    if movie is not None:
        _queue_missing_softsub(movie, kind='movie')

    # Watch-page SoftSub poll: bypass Redis/CDN so newly extracted tracks appear
    # without waiting for the detail TTL.
    if str(request.GET.get('softsub_poll') or '').strip() in {'1', 'true', 'yes'}:
        fresh = get_object_or_404(
            Movie.objects.filter(is_published=True)
            .prefetch_related('genres', 'movie_actors__actor', 'directors', 'countries', 'tags'),
            slug=slug,
        )
        response = Response(MovieDetailSerializer(fresh).data)
        response['Cache-Control'] = 'private, no-store'
        response['X-Catalog-Cache'] = 'BYPASS'
        return response

    return _cached_response(request, f'movie:{slug}', 'detail', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def series_list(request):
    queryset = Series.objects.filter(is_published=True)
    status = request.GET.get('status')

    if status:
        queryset = queryset.filter(status=status)

    queryset = _apply_catalog_filters(queryset, request, 'start_year').prefetch_related(
        'genres', 'directors', 'countries',
    )
    return _catalog_list_response(request, 'series', queryset, SeriesListSerializer, 'start_year')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def series_detail(request, slug):
    def build():
        playable_episodes = (
            Episode.objects.filter(is_published=True)
            .exclude(video_url='', download_key='')
            .order_by('episode_number')
        )
        published_seasons = (
            Season.objects.filter(is_published=True)
            .filter(Exists(playable_episodes.filter(season_id=OuterRef('pk'))))
            .order_by('season_number')
            .prefetch_related(
                Prefetch('episodes', queryset=playable_episodes, to_attr='published_episodes'),
            )
        )
        series = get_object_or_404(
            Series.objects.filter(is_published=True)
            .prefetch_related(
                'genres', 'directors', 'countries', 'tags', 'series_actors__actor',
                Prefetch('seasons', queryset=published_seasons, to_attr='published_seasons'),
            ),
            slug=slug,
        )
        return SeriesDetailSerializer(series).data

    series = Series.objects.filter(is_published=True, slug=slug).only(
        'id', 'imdb_id', 'download_links', 'title', 'original_title', 'start_year',
    ).first()
    if series is not None:
        _queue_missing_softsub(series, kind='series')

    if str(request.GET.get('softsub_poll') or '').strip() in {'1', 'true', 'yes'}:
        playable_episodes = (
            Episode.objects.filter(is_published=True)
            .exclude(video_url='', download_key='')
            .order_by('episode_number')
        )
        published_seasons = (
            Season.objects.filter(is_published=True)
            .filter(Exists(playable_episodes.filter(season_id=OuterRef('pk'))))
            .order_by('season_number')
            .prefetch_related(
                Prefetch('episodes', queryset=playable_episodes, to_attr='published_episodes'),
            )
        )
        fresh = get_object_or_404(
            Series.objects.filter(is_published=True)
            .prefetch_related(
                'genres', 'directors', 'countries', 'tags', 'series_actors__actor',
                Prefetch('seasons', queryset=published_seasons, to_attr='published_seasons'),
            ),
            slug=slug,
        )
        response = Response(SeriesDetailSerializer(fresh).data)
        response['Cache-Control'] = 'private, no-store'
        response['X-Catalog-Cache'] = 'BYPASS'
        return response

    return _cached_response(request, f'series:{slug}', 'detail', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def movie_similar(request, slug):
    """Published movies genuinely similar to ``slug`` (same director/cast/genres)."""

    def build(limit):
        from apps.recommendations.services import _similar_content

        movie = get_object_or_404(
            Movie.objects.filter(is_published=True)
            .prefetch_related('genres', 'directors', 'countries', 'tags', 'movie_actors__actor'),
            slug=slug,
        )
        return MovieListSerializer(_similar_content(movie, limit=limit), many=True).data

    limit = _bounded_int(request.GET.get('limit'), 8, 1, 24)
    return _cached_response(request, f'similar-movie:{slug}:{limit}', 'detail', lambda: build(limit))


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def series_similar(request, slug):
    """Published series genuinely similar to ``slug`` (same director/cast/genres)."""

    def build(limit):
        from apps.recommendations.services import _similar_content

        series = get_object_or_404(
            Series.objects.filter(is_published=True)
            .prefetch_related('genres', 'directors', 'countries', 'tags', 'series_actors__actor'),
            slug=slug,
        )
        return SeriesListSerializer(_similar_content(series, limit=limit), many=True).data

    limit = _bounded_int(request.GET.get('limit'), 8, 1, 24)
    return _cached_response(request, f'similar-series:{slug}:{limit}', 'detail', lambda: build(limit))


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def recent_catalog(request):
    """Published movies and series mixed by created_at (newest first)."""
    limit = _bounded_int(request.GET.get('limit'), 24, 1, 48)
    offset = _bounded_int(request.GET.get('offset'), 0, 0, 10_000)
    kind = request.GET.get('type', 'all').strip()

    if kind == 'movie':
        queryset = (
            Movie.objects.filter(is_published=True)
            .order_by('-created_at', '-id')
            .defer(
                'description', 'source_metadata', 'manual_override_fields',
                'spoken_languages', 'production_companies', 'crew_metadata',
                'writers', 'content_warnings', 'seo_keywords',
            )
            .prefetch_related('genres', 'directors', 'countries')
        )
        return _paginated_cached_response(
            request, 'recent-movies', queryset, MovieListSerializer, kind='list',
        )
    if kind == 'series':
        queryset = (
            Series.objects.filter(is_published=True)
            .order_by('-created_at', '-id')
            .defer('description', 'source_metadata', 'content_warnings')
            .prefetch_related('genres', 'directors', 'countries')
        )
        return _paginated_cached_response(
            request, 'recent-series', queryset, SeriesListSerializer, kind='list',
        )

    def build():
        # Only pull enough rows from each side to cover this page. The global
        # top (offset+limit) is always contained in the per-type top windows.
        window = offset + limit
        movie_keys = list(
            Movie.objects.filter(is_published=True)
            .order_by('-created_at', '-id')
            .values_list('id', 'created_at')[:window]
        )
        series_keys = list(
            Series.objects.filter(is_published=True)
            .order_by('-created_at', '-id')
            .values_list('id', 'created_at')[:window]
        )
        combined = sorted(
            [('movie', item_id, created_at) for item_id, created_at in movie_keys]
            + [('series', item_id, created_at) for item_id, created_at in series_keys],
            key=lambda row: (row[2], row[1]),
            reverse=True,
        )
        count = (
            Movie.objects.filter(is_published=True).count()
            + Series.objects.filter(is_published=True).count()
        )
        page_keys = combined[offset:offset + limit]
        movie_ids = [item_id for kind_name, item_id, _ in page_keys if kind_name == 'movie']
        series_ids = [item_id for kind_name, item_id, _ in page_keys if kind_name == 'series']
        movies_by_id = {
            movie.id: movie
            for movie in Movie.objects.filter(id__in=movie_ids).prefetch_related(
                'genres', 'directors', 'countries',
            )
        }
        series_by_id = {
            series.id: series
            for series in Series.objects.filter(id__in=series_ids).prefetch_related(
                'genres', 'directors', 'countries',
            )
        }
        results = []
        for kind_name, item_id, _ in page_keys:
            if kind_name == 'movie':
                movie = movies_by_id.get(item_id)
                if not movie:
                    continue
                payload = MovieListSerializer(movie).data
                payload['content_type'] = 'movie'
                results.append(payload)
            else:
                series = series_by_id.get(item_id)
                if not series:
                    continue
                payload = SeriesListSerializer(series).data
                payload['content_type'] = 'series'
                results.append(payload)

        next_offset = offset + limit
        previous_offset = offset - limit
        base = request.path
        query = request.GET.copy()
        payload = {
            'count': count,
            'next': None,
            'previous': None,
            'results': results,
        }
        if next_offset < count:
            query['limit'] = str(limit)
            query['offset'] = str(next_offset)
            payload['next'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
        if previous_offset >= 0:
            query['limit'] = str(limit)
            query['offset'] = str(previous_offset)
            payload['previous'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
        elif offset > 0:
            query['limit'] = str(limit)
            query['offset'] = '0'
            payload['previous'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
        return payload

    return _cached_response(request, 'recent-catalog', 'list', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def genre_list(request):
    def build():
        # Two grouped scans beat per-genre filtered Count(distinct) on large M2M tables.
        movie_map = {
            int(row['genres']): int(row['c'])
            for row in (
                Movie.objects.filter(is_published=True, genres__isnull=False)
                .values('genres')
                .annotate(c=Count('id', distinct=True))
            )
            if row.get('genres') is not None
        }
        series_map = {
            int(row['genres']): int(row['c'])
            for row in (
                Series.objects.filter(is_published=True, genres__isnull=False)
                .values('genres')
                .annotate(c=Count('id', distinct=True))
            )
            if row.get('genres') is not None
        }
        payload = []
        for genre in Genre.objects.all().order_by('-is_featured', 'title').only(
            'id', 'title', 'slug', 'is_featured',
        ):
            movie_count = movie_map.get(genre.id, 0)
            series_count = series_map.get(genre.id, 0)
            payload.append({
                'id': genre.id,
                'title': genre.title,
                'slug': genre.slug,
                'is_featured': bool(genre.is_featured),
                'movie_count': movie_count,
                'series_count': series_count,
                'title_count': movie_count + series_count,
            })
        return payload

    return _cached_response(request, 'genres', 'genres', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def home_rails(request):
    """Home discovery rails scored on the backend (featured / dubbed / popular series)."""
    limit = _bounded_int(request.GET.get('limit'), 7, 1, 24)

    def build():
        from apps.catalog.trending import build_home_rails, rail_rotation_meta

        rails = build_home_rails(limit=limit)
        meta = rails.get('meta') or rail_rotation_meta()
        return {
            'meta': meta,
            'featured': MovieListSerializer(rails['featured'], many=True).data,
            'dubbed': MovieListSerializer(rails['dubbed'], many=True).data,
            'popular_series': SeriesListSerializer(rails['popular_series'], many=True).data,
        }

    # Include rotation bucket in namespace so CDN/cache keys rotate with the slot.
    from apps.catalog.trending import rail_rotation_meta
    meta = rail_rotation_meta()
    namespace = f"home-rails:{meta.get('day')}:{meta.get('bucket')}:{limit}"
    return _cached_response(request, namespace, 'home', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def country_list(request):
    def build():
        queryset = (
            Country.objects.annotate(
                movie_count=Count('movies', filter=Q(movies__is_published=True), distinct=True),
                series_count=Count('series', filter=Q(series__is_published=True), distinct=True),
            )
            .filter(Q(movie_count__gt=0) | Q(series_count__gt=0))
            .order_by('name')
        )
        return CountrySerializer(queryset, many=True).data

    return _cached_response(request, 'countries', 'genres', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def actor_list(request):
    """Actors that appear on at least one published title, popular first."""
    queryset = (
        Actor.objects.filter(
            Q(movies__is_published=True) | Q(series__is_published=True),
        )
        .distinct()
        .order_by('-is_featured', '-popularity', 'name')
    )
    featured = request.GET.get('featured')
    if featured in {'1', 'true', 'yes'}:
        queryset = queryset.filter(is_featured=True)
    return _paginated_cached_response(request, 'actors', queryset, ActorListSerializer, kind='actors')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def actor_detail(request, slug):
    def build():
        actor = get_object_or_404(Actor.objects.all(), slug=slug)
        return ActorDetailSerializer(actor, context={'request': request}).data

    return _cached_response(request, f'actor:{slug}', 'detail', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def director_list(request):
    queryset = Director.objects.all().order_by('name')
    return _paginated_cached_response(request, 'directors', queryset, DirectorListSerializer, kind='actors')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def director_detail(request, slug):
    def build():
        director = get_object_or_404(Director.objects.all(), slug=slug)
        return DirectorListSerializer(director).data

    return _cached_response(request, f'director:{slug}', 'detail', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def search_content(request):
    q = request.GET.get('q', '').strip()[:120]
    parsed_query = parse_search_query(q)
    search_text = parsed_query.text
    search_year = _bounded_int(
        normalize_search_digits(request.GET.get('year')),
        parsed_query.year,
        1888,
        2100,
    )
    content_type = request.GET.get('type', 'all')
    limit = _bounded_int(request.GET.get('limit'), 12, 1, 24)
    if content_type not in {'all', 'movie', 'series', 'actor'}:
        content_type = 'all'

    # One-character live-search probes match a large fraction of titles and
    # people while providing little useful intent. Waiting for two characters
    # prevents a request-per-keystroke stampede on the public endpoint.
    if not search_year and len(normalize_search_text(search_text).replace(' ', '')) < 2:
        response = Response({
            'query': q,
            'search_text': search_text,
            'year': search_year,
            'match_type': 'none',
            'movies': [],
            'series': [],
            'actors': [],
        })
        response['Cache-Control'] = 'public, max-age=15'
        return response

    def build():
        variants = search_query_variants(search_text)
        title_q = title_search_q(search_text) if search_text else Q()
        resolved_related = None

        def scoped_queryset(model):
            source = model.objects.filter(is_published=True)
            if search_year is not None:
                year_field = 'release_year' if model is Movie else 'start_year'
                source = source.filter(**{year_field: search_year})
            return source

        def text_query(*fields):
            return _text_search_q(variants, *fields)

        def ranked_title_ids(model, base_q, *, queryset=None):
            source = queryset if queryset is not None else scoped_queryset(model)
            return list(
                source.filter(base_q)
                .annotate(search_rank=title_rank_annotation(search_text))
                .order_by('-search_rank', '-view_count', '-popularity', '-created_at')
                .values_list('id', flat=True)[:limit]
            )

        def ranked_year_ids(model):
            return list(
                scoped_queryset(model)
                .order_by('-view_count', '-popularity', '-created_at')
                .values_list('id', flat=True)[:limit]
            )

        def ranked_broad_ids(model):
            nonlocal resolved_related
            if resolved_related is None:
                resolved_related = _resolve_related_search_ids(
                    variants,
                    include_genres=True,
                )
            broad_match = (
                _related_catalog_search_q(
                    model,
                    include_genres=True,
                    resolved=resolved_related,
                )
            )
            return ranked_title_ids(model, broad_match)

        def serialize_ranked(model, serializer_class, ids):
            if not ids:
                return []
            queryset = (
                model.objects.filter(id__in=ids, is_published=True)
                .prefetch_related('genres', 'directors', 'countries')
            )
            by_id = {item.id: item for item in queryset}
            ordered = [by_id[item_id] for item_id in ids if item_id in by_id]
            return serializer_class(ordered, many=True).data

        movie_ids = []
        series_ids = []
        title_hit = False
        if search_text:
            if content_type in ('all', 'movie'):
                movie_ids = ranked_title_ids(Movie, title_q)
            if content_type in ('all', 'series'):
                series_ids = ranked_title_ids(Series, title_q)
        elif search_year is not None:
            if content_type in ('all', 'movie'):
                movie_ids = ranked_year_ids(Movie)
            if content_type in ('all', 'series'):
                series_ids = ranked_year_ids(Series)
        title_hit = bool(movie_ids or series_ids)

        # Broader DB probe only when titles/slugs miss — keeps new catalog rows
        # discoverable via synopsis/people without drowning exact title matches.
        if search_text and not title_hit:
            if content_type in ('all', 'movie'):
                movie_ids = ranked_broad_ids(Movie)
            if content_type in ('all', 'series'):
                series_ids = ranked_broad_ids(Series)

        direct_media_found = bool(movie_ids or series_ids)
        normalized_exact_found = False
        if search_text and not direct_media_found:
            if content_type in ('all', 'movie'):
                movie_ids, movie_exact = rank_similar_title_ids(
                    scoped_queryset(Movie), search_text, limit,
                )
                normalized_exact_found = normalized_exact_found or movie_exact
            if content_type in ('all', 'series'):
                series_ids, series_exact = rank_similar_title_ids(
                    scoped_queryset(Series), search_text, limit,
                )
                normalized_exact_found = normalized_exact_found or series_exact

        actor_ids = []
        if search_text and search_year is None and content_type in ('all', 'actor'):
            if resolved_related is None:
                resolved_related = _resolve_related_search_ids(variants)
            candidate_actor_ids = resolved_related['actor_ids']
            actor_ids = list(
                Actor.objects.filter(id__in=candidate_actor_ids)
                .annotate(
                    search_rank=Case(
                        *[
                            When(name__iexact=variant, then=Value(100))
                            for variant in variants
                        ],
                        *[
                            When(original_name__iexact=variant, then=Value(95))
                            for variant in variants
                        ],
                        *[
                            When(name__istartswith=variant, then=Value(80))
                            for variant in variants
                        ],
                        *[
                            When(original_name__istartswith=variant, then=Value(75))
                            for variant in variants
                        ],
                        default=Value(20),
                        output_field=IntegerField(),
                    ),
                )
                .order_by('-search_rank', '-popularity', 'name')
                .values_list('id', flat=True)[:limit]
            )

        if title_hit or actor_ids or normalized_exact_found:
            match_type = 'direct'
        elif direct_media_found:
            match_type = 'direct'
        elif movie_ids or series_ids:
            match_type = 'similar'
        else:
            match_type = 'none'

        results = {
            'query': q,
            'search_text': search_text,
            'year': search_year,
            'match_type': match_type,
            'movies': serialize_ranked(Movie, MovieListSerializer, movie_ids)
            if content_type in ('all', 'movie') else [],
            'series': serialize_ranked(Series, SeriesListSerializer, series_ids)
            if content_type in ('all', 'series') else [],
            'actors': [],
        }
        if actor_ids:
            actors = Actor.objects.filter(id__in=actor_ids)
            actors_by_id = {actor.id: actor for actor in actors}
            results['actors'] = ActorListSerializer(
                [actors_by_id[actor_id] for actor_id in actor_ids if actor_id in actors_by_id],
                many=True,
            ).data

        return results

    return _cached_response(request, 'search', 'search', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def trending(request):
    content_type = request.GET.get('type', 'all')
    limit = _bounded_int(request.GET.get('limit'), 20, 1, 50)

    def build():
        from apps.catalog.trending import trending_queryset

        results = {}

        if content_type in ('all', 'movie'):
            movies = trending_queryset(Movie, limit=limit)
            results['movies'] = MovieListSerializer(movies, many=True).data

        if content_type in ('all', 'series'):
            series = trending_queryset(Series, limit=limit)
            results['series'] = SeriesListSerializer(series, many=True).data

        return results

    return _cached_response(request, 'trending', 'trending', build)


@api_view(['POST'])
@throttle_classes([PlaybackSubtitleEnsureThrottle])
def playback_subtitle_ensure(request):
    """Report a missing SoftSub on the online player and urgently attach cues.

    Order: embedded movie/episode track → SubtitleStar → Subzone/provider fallbacks.
    Body: ``{ content_type, slug, episode_id?, version?, source_url?, sync? }``
    """
    from apps.catalog.playback_subtitle import ensure_playback_subtitles

    payload = request.data if isinstance(request.data, dict) else {}
    sync_raw = payload.get('sync', True)
    if isinstance(sync_raw, str):
        sync = sync_raw.strip().lower() not in {'0', 'false', 'no'}
    else:
        sync = bool(sync_raw)

    result = ensure_playback_subtitles(
        content_type=str(payload.get('content_type') or payload.get('type') or ''),
        slug=str(payload.get('slug') or ''),
        episode_id=payload.get('episode_id') or payload.get('episode') or 0,
        playback_version=str(payload.get('version') or payload.get('playback_version') or ''),
        playback_source_url=str(payload.get('source_url') or payload.get('playback_source_url') or ''),
        sync=sync,
        timeout_seconds=14,
    )
    response = Response(result)
    response['Cache-Control'] = 'private, no-store'
    return response
