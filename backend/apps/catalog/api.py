from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

from django.core.cache import cache
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Prefetch, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .cache import (
    cache_control_for,
    cached_catalog_payload,
)
from .countries import country_code_for_name, persian_country_name
from .models import (
    Actor, Collection, Country, Director, Episode, Genre, Movie, MovieActor, Season,
    Series, SeriesActor,
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
from .slugs import canonical_slug
from .serializers import (
    ActorDetailSerializer, ActorListSerializer, CollectionDetailSerializer,
    CollectionListSerializer, CountrySerializer, DirectorDetailSerializer, DirectorListSerializer,
    GenreListSerializer, GenreSerializer, MovieDetailSerializer, MovieListSerializer,
    SeriesDetailSerializer, SeriesListSerializer,
)


class CatalogReadThrottle(AnonRateThrottle):
    scope = 'catalog'


class PlaybackSubtitleEnsureThrottle(AnonRateThrottle):
    """Allow a few urgent SoftSub ensures per client without starving catalog reads."""

    scope = 'playback_subtitle_ensure'


class PlaybackSubtitleStatusThrottle(AnonRateThrottle):
    """Lightweight player poll bucket; never shares the heavy ensure budget."""

    scope = 'playback_subtitle_status'


class ContentIssueReportThrottle(AnonRateThrottle):
    """In-player «گزارش خطا» intake; a few reports per client per minute."""

    scope = 'content_issue_report'


class ContentIssueStatusThrottle(AnonRateThrottle):
    """Player poll for a filed report's remediation status."""

    scope = 'content_issue_status'


class SubtitleSyncReportThrottle(AnonRateThrottle):
    """One-vote-per-viewer feedback; a small bucket keeps spam off the consensus."""

    scope = 'subtitle_sync_report'


class PlaybackFailureThrottle(AnonRateThrottle):
    """Automatic player-failure intake; shares the report budget, not catalog reads."""

    scope = 'playback_failure'


def _queue_missing_softsub(obj, *, kind: str) -> None:
    """Best-effort SoftSub / SubtitleStar backfill when a public detail page is viewed."""
    try:
        from django.conf import settings
        from apps.catalog.subtitle_extract import (
            download_links_imply_softsub,
            normalize_imdb_id_safe,
        )
        from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
        from apps.catalog.playback_subtitle import _has_tracks

        links = [item for item in (getattr(obj, 'download_links', None) or []) if isinstance(item, dict)]
        if kind == 'movie':
            # A truthy but malformed/stale track must not disable automatic
            # repair.  Use the same readiness contract as the player.
            if _has_tracks(getattr(obj, 'subtitle_tracks', None)):
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
            from apps.catalog.models import Episode

            # Keep queueing while any published episode still lacks a usable
            # SoftSub track. Checking merely ``[]``/NULL misses malformed or
            # stale track rows and leaves the player permanently unsubtitled.
            episode_tracks = Episode.objects.filter(
                season__series_id=obj.pk,
                is_published=True,
            ).values_list('subtitle_tracks', flat=True).iterator(chunk_size=100)
            missing_tracks = any(not _has_tracks(tracks) for tracks in episode_tracks)
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


def _cached_response(request, namespace: str, kind: str, builder, *, allow_stale: bool = True):
    """Serve anonymous catalog JSON from Redis when available."""
    payload, state = cached_catalog_payload(namespace, request, kind, builder, allow_stale=allow_stale)
    response = Response(payload)
    response['Cache-Control'] = cache_control_for(kind)
    response['X-Catalog-Cache'] = state
    return response


def _relative_pagination_link(url):
    """Keep path+query only so Redis-cached pages work for SSR and browsers."""
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit(('', '', parts.path, parts.query, '')) or None


def _paginated_cached_response(request, namespace: str, queryset, serializer_class, kind='list'):
    def build():
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is None:
            return serializer_class(queryset, many=True).data
        return {
            'count': paginator.count,
            'next': _relative_pagination_link(paginator.get_next_link()),
            'previous': _relative_pagination_link(paginator.get_previous_link()),
            'results': serializer_class(page, many=True).data,
        }

    return _cached_response(request, namespace, kind, build)


def _age_band_raw_values(model):
    """Distinct stored age certifications, cached: the table scan below ran on
    every age-filtered list request and never changes within the hour."""
    key = f'catalog:age_ratings:{model.__name__}'
    try:
        values = cache.get(key)
    except Exception:
        values = None
    if values is None:
        values = list(
            model.objects.exclude(age_rating='')
            .values_list('age_rating', flat=True)
            .distinct()
        )
        try:
            cache.set(key, values, timeout=3600)
        except Exception:
            pass
    return values


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
        from .age_ratings import BANDS, raw_ratings_in_band

        if age_rating in BANDS:
            # Rows store the board's own certification (R, PG-13, 15…); the
            # site filters by the band it shows.
            raw_values = _age_band_raw_values(queryset.model)
            queryset = queryset.filter(age_rating__in=raw_ratings_in_band(raw_values, age_rating))
        else:
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

    def build():
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
        return payload

    return _cached_response(request, namespace, kind, build)


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
    slug = canonical_slug(Movie, slug)

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
    slug = canonical_slug(Series, slug)

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
    slug = canonical_slug(Movie, slug)

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
    slug = canonical_slug(Series, slug)

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
def weekly_schedule(request):
    """Weekly airing schedule: what aired on each day and is on the site now.

    Only releases a viewer can play or download are listed (a date alone is
    not worth a card). The window is the ``days`` days that end on ``end``
    (default: today, Tehran time; never later than today), newest last.
    """
    import datetime

    from .airing import today_tehran
    from .schedule import DEFAULT_DAYS, build_weekly_schedule

    days = _bounded_int(request.GET.get('days'), DEFAULT_DAYS, 1, 21)
    include_movies = request.GET.get('movies', '1').strip().lower() not in {'0', 'false', 'no'}

    today = today_tehran()
    end = today
    raw_end = (request.GET.get('end') or '').strip()
    if raw_end:
        try:
            end = min(datetime.date.fromisoformat(raw_end), today)
        except ValueError:
            end = today
    start = end - datetime.timedelta(days=days - 1)

    def build():
        return build_weekly_schedule(
            start=start, days=days, include_movies=include_movies, available_only=True,
        )

    return _cached_response(request, 'weekly-schedule', 'list', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def anime_catalog(request):
    """Published anime — movies and series carrying the `anime` genre — mixed by
    created_at (newest first). Powers the site's dedicated anime shelves."""
    limit = _bounded_int(request.GET.get('limit'), 24, 1, 48)
    offset = _bounded_int(request.GET.get('offset'), 0, 0, 10_000)
    kind = request.GET.get('type', 'all').strip()

    movie_base = Movie.objects.filter(is_published=True, genres__slug='anime')
    series_base = Series.objects.filter(is_published=True, genres__slug='anime')

    if kind == 'movie':
        queryset = (
            movie_base.order_by('-created_at', '-id')
            .defer(
                'description', 'source_metadata', 'manual_override_fields',
                'spoken_languages', 'production_companies', 'crew_metadata',
                'writers', 'content_warnings', 'seo_keywords',
            )
            .prefetch_related('genres', 'directors', 'countries')
        )
        return _paginated_cached_response(
            request, 'anime-movies', queryset, MovieListSerializer, kind='list',
        )
    if kind == 'series':
        queryset = (
            series_base.order_by('-created_at', '-id')
            .defer('description', 'source_metadata', 'content_warnings')
            .prefetch_related('genres', 'directors', 'countries')
        )
        return _paginated_cached_response(
            request, 'anime-series', queryset, SeriesListSerializer, kind='list',
        )

    def build():
        window = offset + limit
        movie_keys = list(
            movie_base.order_by('-created_at', '-id').values_list('id', 'created_at')[:window]
        )
        series_keys = list(
            series_base.order_by('-created_at', '-id').values_list('id', 'created_at')[:window]
        )
        combined = sorted(
            [('movie', item_id, created_at) for item_id, created_at in movie_keys]
            + [('series', item_id, created_at) for item_id, created_at in series_keys],
            key=lambda row: (row[2], row[1]),
            reverse=True,
        )
        count = movie_base.count() + series_base.count()
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

    return _cached_response(request, 'anime-catalog', 'list', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def imdb_top250(request):
    """The IMDb Top 250 shelves, in chart order.

    ``type`` is ``movie`` (default) or ``series``. Every chart position is
    returned — a title we can already play carries the full list-card payload
    plus ``available: true``; a position still being completed carries only
    the chart facts (rank, title, year, score) and ``available: false`` so the
    page can show the whole list honestly. ``available=1`` narrows the result to
    playable positions (what rails and the app grid use). ``coverage`` reports
    how complete each shelf is.
    """
    from .models import ImdbChartEntry
    from .top250 import coverage

    kind = request.GET.get('type', 'movie').strip().lower()
    if kind not in ('movie', 'series'):
        kind = 'movie'
    only_available = str(request.GET.get('available', '')).strip().lower() in {'1', 'true', 'yes'}
    limit = _bounded_int(request.GET.get('limit'), 50, 1, 250)
    offset = _bounded_int(request.GET.get('offset'), 0, 0, 250)

    def build():
        entries = ImdbChartEntry.objects.filter(kind=kind).order_by('rank')
        if only_available:
            published = {f'{kind}__is_published': True}
            entries = entries.filter(**published)
        count = entries.count()
        page = list(entries[offset:offset + limit].values(
            'rank', 'imdb_id', 'primary_title', 'original_title', 'start_year',
            'average_rating', 'num_votes', kind,
        ))
        model, serializer = (Movie, MovieListSerializer) if kind == 'movie' else (Series, SeriesListSerializer)
        ids = [row[kind] for row in page if row[kind]]
        items = {
            obj.id: obj
            for obj in model.objects.filter(id__in=ids, is_published=True).prefetch_related(
                'genres', 'directors', 'countries',
            )
        }
        results = []
        for row in page:
            obj = items.get(row[kind])
            rating = float(row['average_rating']) if row['average_rating'] is not None else None
            if obj is not None:
                payload = serializer(obj).data
                payload['available'] = True
            else:
                payload = {
                    'id': None,
                    'slug': None,
                    'title': row['primary_title'],
                    'english_title': row['primary_title'],
                    'original_title': row['original_title'],
                    'year': row['start_year'],
                    'imdb_rating': rating,
                    'poster': None,
                    'available': False,
                }
            payload['content_type'] = kind
            payload['imdb_rank'] = row['rank']
            payload['imdb_id'] = row['imdb_id']
            payload['imdb_votes'] = row['num_votes']
            results.append(payload)

        base = request.path
        query = request.GET.copy()
        query['limit'] = str(limit)
        payload = {'count': count, 'next': None, 'previous': None, 'results': results}
        if offset + limit < count:
            query['offset'] = str(offset + limit)
            payload['next'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
        if offset > 0:
            query['offset'] = str(max(0, offset - limit))
            payload['previous'] = _relative_pagination_link(f'{base}?{query.urlencode()}')
        payload['coverage'] = coverage().get(kind, {})
        return payload

    return _cached_response(request, 'imdb-top250', 'list', build)


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
    platform = (request.GET.get('platform') or '').strip().lower() or None

    def build():
        from apps.catalog.trending import build_home_rails, rail_rotation_meta

        rails = build_home_rails(limit=limit)
        meta = rails.get('meta') or rail_rotation_meta()
        # The main slider is admin-curated (is_featured + featured_order) and
        # covers movies and series for the requesting platform (web/app/both).
        # Kept separate from the scored featured rail: popularity must never
        # push an unverified title into the main slider.
        return {
            'meta': meta,
            'hero': serialize_slider_items(platform=platform, limit=limit),
            'featured': MovieListSerializer(rails['featured'], many=True).data,
            'dubbed': MovieListSerializer(rails['dubbed'], many=True).data,
            'popular_series': SeriesListSerializer(rails['popular_series'], many=True).data,
        }

    # Include rotation bucket + platform in namespace so CDN/cache keys rotate
    # with the slot and never serve the app slider to the web or vice versa.
    # No stale serving here: the hero is admin-curated, the build is ~0.3 s,
    # and a stale hero after an editorial save reads as panel/site disagreement.
    from apps.catalog.trending import rail_rotation_meta
    meta = rail_rotation_meta()
    namespace = f"home-rails:{meta.get('day')}:{meta.get('bucket')}:{limit}:{platform or 'all'}"
    return _cached_response(request, namespace, 'home', build, allow_stale=False)


def serialize_slider_items(*, platform=None, limit=24):
    """Admin-ordered slider cards with an explicit ``content_type`` per item."""
    from apps.catalog.slider import slider_items

    cards = []
    for entry in slider_items(platform=platform, limit=limit):
        kind = entry.get('content_type')
        if kind == 'series':
            payload = SeriesListSerializer(entry['series']).data
        else:
            payload = MovieListSerializer(entry['movie']).data
            kind = 'movie'
        payload['content_type'] = kind
        cards.append(payload)
    return cards


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def home_slider(request):
    """Admin-curated home slider for the website and the application.

    ``?platform=web|app`` (default ``all``) selects which client the list is
    for; ``?limit=`` caps the items (1–30, default 10). Every card carries
    ``content_type`` (``movie``/``series``) so both clients render the right
    detail route without guessing from the year shape.
    """
    limit = _bounded_int(request.GET.get('limit'), 10, 1, 30)
    platform = (request.GET.get('platform') or '').strip().lower() or None

    def build():
        return {
            'platform': platform or 'all',
            'results': serialize_slider_items(platform=platform, limit=limit),
        }

    # No stale serving: admin-curated, ~0.2 s to build, and both clients must
    # agree with the panel the moment a save lands.
    namespace = f"home-slider:{platform or 'all'}:{limit}"
    return _cached_response(request, namespace, 'slider', build, allow_stale=False)


def _country_options_payload():
    """Published-country options with per-type counts.

    Two grouped scans beat per-country filtered Count(distinct) on large
    M2M tables — the same pattern as genre_list.
    """
    movie_map = {
        int(row['countries']): int(row['c'])
        for row in (
            Movie.objects.filter(is_published=True, countries__isnull=False)
            .values('countries')
            .annotate(c=Count('id', distinct=True))
        )
        if row.get('countries') is not None
    }
    series_map = {
        int(row['countries']): int(row['c'])
        for row in (
            Series.objects.filter(is_published=True, countries__isnull=False)
            .values('countries')
            .annotate(c=Count('id', distinct=True))
        )
        if row.get('countries') is not None
    }
    payload = []
    for country in Country.objects.all().order_by('name').only(
        'id', 'name', 'code',
    ):
        movie_count = movie_map.get(country.id, 0)
        series_count = series_map.get(country.id, 0)
        if not (movie_count or series_count):
            continue
        payload.append({
            'id': country.id,
            'name': persian_country_name(country.code, country.name),
            'code': country.code,
            'movie_count': movie_count,
            'series_count': series_count,
        })
    return payload


def _trending_search_payload(limit=8, min_hits=2):
    """Most-repeated public queries of the last two weeks for search hints."""
    from datetime import timedelta

    from django.db.models import Count, Max
    from django.utils import timezone

    from apps.recommendations.models import SearchLog

    since = timezone.now() - timedelta(days=14)
    # Aggregate latest hit separately so created_at never leaks into GROUP BY
    # (which would split identical queries into single-hit groups).
    rows = (
        SearchLog.objects.filter(created_at__gte=since)
        .values('query')
        .annotate(hits=Count('id'), latest=Max('created_at'))
        .filter(hits__gte=min_hits)
        .order_by('-hits', '-latest')[: limit * 4]
    )
    seen = set()
    payload = []
    for row in rows:
        query = str(row['query'] or '').strip()
        key = normalize_search_text(query)
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        payload.append({'query': query, 'hits': row['hits']})
        if len(payload) >= limit:
            break
    return payload


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def country_list(request):
    return _cached_response(request, 'countries', 'genres', _country_options_payload)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def catalog_filters(request):
    """One-shot filter options so browse pages never render empty dropdowns."""

    def build():
        movie_years = (
            Movie.objects.filter(is_published=True, release_year__isnull=False)
            .values_list('release_year', flat=True)
            .distinct()
        )
        series_years = (
            Series.objects.filter(is_published=True, start_year__isnull=False)
            .values_list('start_year', flat=True)
            .distinct()
        )

        language_values = set()
        raw_languages = list(
            Movie.objects.filter(is_published=True)
            .exclude(language='')
            .values_list('language', flat=True)
            .distinct()
        ) + list(
            Series.objects.filter(is_published=True)
            .exclude(language='')
            .values_list('language', flat=True)
            .distinct()
        )
        for value in raw_languages:
            for token in str(value).split('،'):
                token = token.strip()
                if token:
                    language_values.add(token)

        age_ratings = sorted(
            {
                *Movie.objects.filter(is_published=True)
                .exclude(age_rating='')
                .values_list('age_rating', flat=True)
                .distinct(),
                *Series.objects.filter(is_published=True)
                .exclude(age_rating='')
                .values_list('age_rating', flat=True)
                .distinct(),
            }
        )

        try:
            trending_queries = _trending_search_payload()
        except Exception:
            trending_queries = []

        return {
            'years': sorted({int(y) for y in [*movie_years, *series_years]}, reverse=True),
            'languages': sorted(language_values),
            'age_ratings': age_ratings,
            'trending_queries': trending_queries,
            'countries': _country_options_payload(),
        }

    return _cached_response(request, 'catalog-filters', 'genres', build)


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
    """Directors credited on at least one published title, popular first."""
    queryset = (
        Director.objects.filter(
            Q(movies__is_published=True) | Q(series__is_published=True),
        )
        .distinct()
        .order_by('-is_featured', '-popularity', 'name')
    )
    featured = request.GET.get('featured')
    if featured in {'1', 'true', 'yes'}:
        queryset = queryset.filter(is_featured=True)
    return _paginated_cached_response(request, 'directors', queryset, DirectorListSerializer, kind='actors')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def director_detail(request, slug):
    def build():
        director = get_object_or_404(Director.objects.all(), slug=slug)
        return DirectorDetailSerializer(director, context={'request': request}).data

    return _cached_response(request, f'director:{slug}', 'detail', build)


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def collection_list(request):
    queryset = Collection.objects.filter(is_published=True).order_by('title')
    return _paginated_cached_response(request, 'collections', queryset, CollectionListSerializer, kind='collections')


@api_view(['GET'])
@throttle_classes([CatalogReadThrottle])
def collection_detail(request, slug):
    def build():
        collection = get_object_or_404(
            Collection.objects.filter(is_published=True).prefetch_related('movies', 'series'), slug=slug,
        )
        return CollectionDetailSerializer(collection, context={'request': request}).data

    return _cached_response(request, f'collection:{slug}', 'detail', build)


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
def search_suggest(request):
    """Search-as-you-type: same payload as ``search_content``, answered from the
    in-memory index (``search_suggest.py``) so every keystroke returns in
    milliseconds. The full ``/api/search/`` (synopsis/people/genre probes)
    stays behind the results page."""
    from . import search_suggest as suggest

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
    if content_type not in {'all', 'movie', 'series', 'actor'}:
        content_type = 'all'
    limit = _bounded_int(request.GET.get('limit'), 8, 1, 24)

    if not search_year and not normalize_search_text(search_text):
        response = Response({
            'query': q, 'search_text': search_text, 'year': search_year,
            'match_type': 'none', 'movies': [], 'series': [], 'actors': [],
        })
        response['Cache-Control'] = 'public, max-age=300'
        return response

    def build():
        index = suggest.get_index()
        movie_ids, series_ids, actor_ids = [], [], []
        exact = False
        if content_type in ('all', 'movie'):
            movie_ids, hit = suggest.rank(index.movies, search_text, year=search_year, limit=limit)
            exact = exact or hit
        if content_type in ('all', 'series'):
            series_ids, hit = suggest.rank(index.series, search_text, year=search_year, limit=limit)
            exact = exact or hit
        if search_text and search_year is None and content_type in ('all', 'actor'):
            actor_ids, _ = suggest.rank(index.actors, search_text, year=None, limit=limit)

        match_type = 'direct' if (movie_ids or series_ids or actor_ids) else 'none'
        # Typo tolerance only once the words are long enough to mean something
        # and nothing matched as typed (pg_trgm GIN indexes keep this bounded).
        compact_length = len(normalize_search_text(search_text).replace(' ', ''))
        if not movie_ids and not series_ids and compact_length >= 3:
            def scoped(model):
                source = model.objects.filter(is_published=True)
                if search_year is not None:
                    source = source.filter(**{'release_year' if model is Movie else 'start_year': search_year})
                return source

            if content_type in ('all', 'movie'):
                movie_ids, hit = rank_similar_title_ids(scoped(Movie), search_text, limit)
                exact = exact or hit
            if content_type in ('all', 'series'):
                series_ids, hit = rank_similar_title_ids(scoped(Series), search_text, limit)
                exact = exact or hit
            if movie_ids or series_ids:
                match_type = 'direct' if (exact or actor_ids) else 'similar'

        prefetch = ('genres', 'directors', 'countries')
        return {
            'query': q,
            'search_text': search_text,
            'year': search_year,
            'match_type': match_type,
            'movies': suggest.serialize_cards(Movie, MovieListSerializer, movie_ids, prefetch=prefetch),
            'series': suggest.serialize_cards(Series, SeriesListSerializer, series_ids, prefetch=prefetch),
            'actors': suggest.serialize_cards(Actor, ActorListSerializer, actor_ids),
        }

    return _cached_response(request, 'suggest', 'search', build)


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

    Order: embedded movie/episode track → SubtitleStar → SubDL → Subzone.
    Body: ``{ content_type, slug, episode_id?, version?, source_url?, sync? }``

    The sync lane is intentionally short (PLAYBACK_SUBTITLE_SYNC_MAX_SECONDS) so
    the POST never blocks video start; long extraction runs on the worker.
    """
    from django.conf import settings as django_settings

    from apps.catalog.playback_subtitle import ensure_playback_subtitles

    payload = request.data if isinstance(request.data, dict) else {}
    sync_raw = payload.get('sync', True)
    if isinstance(sync_raw, str):
        sync = sync_raw.strip().lower() not in {'0', 'false', 'no'}
    else:
        sync = bool(sync_raw)

    sync_cap = max(3, int(getattr(django_settings, 'PLAYBACK_SUBTITLE_SYNC_MAX_SECONDS', 6)))
    result = ensure_playback_subtitles(
        content_type=str(payload.get('content_type') or payload.get('type') or ''),
        slug=str(payload.get('slug') or ''),
        episode_id=payload.get('episode_id') or payload.get('episode') or 0,
        playback_version=str(payload.get('version') or payload.get('playback_version') or ''),
        playback_source_url=str(payload.get('source_url') or payload.get('playback_source_url') or ''),
        sync=sync,
        timeout_seconds=min(14, sync_cap),
    )
    response = Response(result)
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
@throttle_classes([PlaybackSubtitleStatusThrottle])
def playback_subtitle_status(request):
    """Lightweight player poll: has the reported gap been filled yet?

    Never enqueues workers or probes providers. Query: ``report_id`` and/or
    ``content_type`` + ``slug`` + ``episode_id``. A short Redis micro-cache keeps
    the DB read cheap across many pollers.
    """
    from apps.catalog.playback_subtitle import read_playback_subtitle_status

    query = request.query_params
    report_id = query.get('report_id')
    episode_id = query.get('episode_id') or query.get('episode') or 0
    result = read_playback_subtitle_status(
        report_id=int(report_id) if str(report_id or '').strip().isdigit() else None,
        content_type=str(query.get('content_type') or query.get('type') or ''),
        slug=str(query.get('slug') or ''),
        episode_id=int(episode_id) if str(episode_id or '').strip().isdigit() else 0,
    )
    response = Response(result)
    response['Cache-Control'] = 'private, no-store'
    return response


def _sync_voter_key(request) -> str:
    """Stable per-viewer id for vote dedup: user id, else hashed session+IP+UA."""
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return f'u{user.pk}'
    import hashlib

    meta = request.META
    forwarded = (meta.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    ip = forwarded or meta.get('REMOTE_ADDR') or ''
    session_key = getattr(getattr(request, 'session', None), 'session_key', '') or ''
    seed = f'{session_key}|{ip}|{meta.get("HTTP_USER_AGENT", "")}'
    return 'a' + hashlib.sha1(seed.encode('utf-8')).hexdigest()[:32]


@api_view(['POST'])
@throttle_classes([SubtitleSyncReportThrottle])
def subtitle_sync_report(request):
    """Record the subtitle timing offset a viewer settled on for a served track.

    Body: ``{ content_type, object_id, track_id, sig, offset, episode_id? }``.
    One row per viewer per track (latest wins); the verifier task later bakes the
    crowd consensus into the file. Never fails player UX — always 200 with ``ok``.
    """
    from apps.catalog.models import SubtitleSyncVote
    from apps.catalog.subtitle_sync import MAX_APPLY_SECONDS

    payload = request.data if isinstance(request.data, dict) else {}
    content_type = str(payload.get('content_type') or payload.get('type') or '').strip().lower()
    track_id = str(payload.get('track_id') or payload.get('track') or '').strip()[:80]
    sig = str(payload.get('sig') or payload.get('sync_sig') or '').strip()[:32]

    try:
        object_id = int(payload.get('object_id') or payload.get('id') or 0)
    except (TypeError, ValueError):
        object_id = 0
    try:
        episode_id = int(payload.get('episode_id') or payload.get('episode') or 0)
    except (TypeError, ValueError):
        episode_id = 0
    try:
        offset = round(float(payload.get('offset')), 3)
    except (TypeError, ValueError):
        offset = None

    ok = bool(
        content_type in {'movie', 'series'}
        and object_id > 0
        and track_id
        and sig
        and offset is not None
        and abs(offset) <= MAX_APPLY_SECONDS
    )
    if ok:
        try:
            SubtitleSyncVote.objects.update_or_create(
                content_type=content_type,
                object_id=object_id,
                episode_id=episode_id if content_type == 'series' else 0,
                track_id=track_id,
                voter_key=_sync_voter_key(request),
                defaults={'sig': sig, 'offset': offset},
            )
        except Exception:  # noqa: BLE001 — telemetry must never break playback
            import logging

            logging.getLogger(__name__).warning('subtitle sync vote failed', exc_info=True)
            ok = False

    response = Response({'ok': ok})
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['POST'])
@throttle_classes([ContentIssueReportThrottle])
def report_content_issue(request):
    """File a structured in-player content-issue report and auto-remediate.

    Body: ``{ content_type, problem_type, object_id?, slug?, episode_id?,
    version?, source_url?, detail? }``. ``problem_type`` is one of the values
    ``GET /api/catalog/report-issue/options/`` serves; the retired coarse
    spellings (``subtitle``, ``audio``) are still accepted and mapped onto the
    precise button they meant, so an older app keeps working.

    The report is deduped, mirrored to the staff inbox and — for fixable types —
    remediated inline through the crawler/classifier that already handles it
    (see :mod:`apps.catalog.content_remediation`). Never blocks player UX.
    """
    from apps.catalog.content_reports import record_content_issue_report

    payload = request.data if isinstance(request.data, dict) else {}

    def _int(*keys):
        for key in keys:
            raw = payload.get(key)
            if str(raw or '').strip().isdigit():
                return int(raw)
        return 0

    result = record_content_issue_report(
        request,
        content_type=str(payload.get('content_type') or payload.get('type') or ''),
        problem_type=str(payload.get('problem_type') or payload.get('problem') or ''),
        object_id=_int('object_id', 'id'),
        slug=str(payload.get('slug') or ''),
        episode_id=_int('episode_id', 'episode'),
        playback_version=str(payload.get('version') or payload.get('playback_version') or ''),
        source_url=str(payload.get('source_url') or payload.get('src') or ''),
        detail=str(payload.get('detail') or payload.get('note') or ''),
    )
    response = Response(result, status=200 if result.get('ok') else 400)
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
@throttle_classes([ContentIssueStatusThrottle])
def content_issue_status(request):
    """Player poll: has a filed content-issue report been auto-fixed yet?

    Query: ``report_id``. Never enqueues work — a pure status read.
    Enriched with the title's *current* servable URL so a fixed player can
    retry without another round-trip.
    """
    from apps.catalog.content_reports import read_report_status
    from apps.catalog.playback_failure import USER_MESSAGES_FA, fixed_playback_for

    report_id = request.query_params.get('report_id')
    if not str(report_id or '').strip().isdigit():
        return Response({'ok': False, 'error': 'report_id_required'}, status=400)
    result = read_report_status(int(report_id))
    if result.get('ok'):
        try:
            from apps.catalog.models import ContentIssueReport

            report = ContentIssueReport.objects.filter(pk=int(report_id)).only(
                'content_type', 'object_id', 'episode_id', 'status',
            ).first()
            if report is not None:
                from apps.catalog.playback_api import resolve_target

                kind = report.content_type
                obj_id = report.object_id if kind != 'series' or not report.episode_id else report.object_id
                # For series episode reports resolve via episode id.
                if kind == 'series' and report.episode_id:
                    owner, episode = resolve_target('episode', report.episode_id)
                else:
                    owner, episode = resolve_target(kind, obj_id)
                if owner is not None:
                    fixed = fixed_playback_for(owner, episode)
                    result['fixed_url'] = fixed.get('url') or ''
                    result['playback_mode'] = fixed.get('playback_mode') or ''
                    result['has_fixed_url'] = bool(fixed.get('has_url'))
                else:
                    result['fixed_url'] = ''
                    result['playback_mode'] = ''
                    result['has_fixed_url'] = False
                status = str(result.get('status') or '')
                if result.get('resolved'):
                    result['message_fa'] = USER_MESSAGES_FA['fixed']
                elif status in {'queued', 'open', 'remediating'}:
                    result['message_fa'] = USER_MESSAGES_FA['queued']
                elif status == 'needs_review':
                    result['message_fa'] = USER_MESSAGES_FA['needs_review']
                elif status == 'unavailable':
                    result['message_fa'] = USER_MESSAGES_FA['unavailable']
                else:
                    result['message_fa'] = USER_MESSAGES_FA['received']
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            pass
    response = Response(result)
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
def content_issue_options(request):
    """The «گزارش خطا» buttons this player should render.

    Query: ``content_type`` (``movie``/``series``) and ``episode_id`` — both
    optional, and both only narrow the list: «قسمت اشتباه» is dropped for a film
    and for a series whose player has not told us which episode is on screen,
    because a report the intake would immediately reject is worse than no button.

    Clients ship a bundled copy of this list for first paint and offline use, so
    the response is cacheable and ordinary; the point of serving it is that a new
    repair in :mod:`apps.catalog.content_remediation` becomes a new button
    everywhere without an app release.
    """
    from apps.catalog.report_catalog import grouped_for

    content_type = str(request.query_params.get('content_type') or request.query_params.get('type') or '')
    episode_id = str(request.query_params.get('episode_id') or request.query_params.get('episode') or '')
    groups = grouped_for(content_type, has_episode=episode_id.strip().isdigit() and int(episode_id) > 0)

    response = Response({
        'ok': True,
        'groups': groups,
        'options': [option for group in groups for option in group['options']],
    })
    # Identical for every viewer of a given content type, and it changes only
    # when we ship a new repair.
    response['Cache-Control'] = 'public, max-age=300, stale-while-revalidate=3600'
    return response


@api_view(['POST'])
@throttle_classes([PlaybackFailureThrottle])
def playback_failure_report(request):
    """Automatic intake for a failed online playback (single or watch-party).

    The player calls this the moment ``<video>`` fails — not after the viewer
    finds the «گزارش خطا» button. Body::

        { content_type, object_id?, slug?, episode_id?,
          error_code?, error_message?, gateway_code?,
          source_url?, version?, player?, room_code?,
          played_seconds?, had_played?, problem_type? (optional hint) }

    The failure is classified by :mod:`apps.catalog.playback_failure` onto the
    exact ``problem_type`` a manual report would have used, filed through the
    same deduped :func:`record_content_issue_report` path (so popular breakages
    still surface once), and remediated through the same engine. The response
    carries what the player needs to recover *now* — ``fixed_url`` when the
    catalog already serves something better, plus a Persian ``message_fa`` to
    show — and, for watch-party rooms, the fix is also broadcast to the room.

    Never fails player UX: always 200 with ``ok``.
    """
    from apps.catalog.content_reports import record_content_issue_report
    from apps.catalog.playback_failure import (
        USER_MESSAGES_FA,
        build_auto_detail,
        classify_failure,
        fixed_playback_for,
    )

    payload = request.data if isinstance(request.data, dict) else {}

    def _int(*keys):
        for key in keys:
            raw = payload.get(key)
            if str(raw or '').strip().isdigit():
                return int(raw)
        return 0

    def _float(key, default=0.0):
        try:
            return float(payload.get(key) or default)
        except (TypeError, ValueError):
            return default

    content_type = str(payload.get('content_type') or payload.get('type') or '').strip().lower()
    slug = str(payload.get('slug') or '').strip()[:255]
    object_id = _int('object_id', 'id')
    episode_id = _int('episode_id', 'episode')
    error_code = str(payload.get('error_code') or payload.get('code') or '')[:32]
    error_message = str(payload.get('error_message') or payload.get('message') or '')[:500]
    gateway_code = str(payload.get('gateway_code') or payload.get('gateway') or '')[:32]
    source_url = str(payload.get('source_url') or payload.get('sourceUrl') or payload.get('src') or '')[:1000]
    version = str(payload.get('version') or payload.get('playback_version') or '')[:32]
    player = str(payload.get('player') or '')[:16] or 'web'
    room_code = str(payload.get('room_code') or payload.get('roomCode') or payload.get('invite_code') or '')[:32]
    hint_problem = str(payload.get('problem_type') or payload.get('problem') or '')
    played_seconds = _float('played_seconds', _float('position_seconds', 0.0))
    had_played = str(payload.get('had_played') or '').strip().lower() in {'1', 'true', 'yes'} or played_seconds > 1

    classification = classify_failure(
        error_code=error_code,
        error_message=error_message,
        gateway_code=gateway_code,
        source_url=source_url,
        played_seconds=played_seconds,
        had_played=had_played,
        hint_problem=hint_problem,
    )
    problem_type = classification['problem_type']
    detail = build_auto_detail(
        error_code=error_code or classification.get('reason', ''),
        error_message=error_message,
        gateway_code=gateway_code,
        player=player,
        room_code=room_code,
    )

    result = record_content_issue_report(
        request,
        content_type=content_type,
        problem_type=problem_type,
        object_id=object_id,
        slug=slug,
        episode_id=episode_id,
        playback_version=version,
        source_url=source_url,
        detail=detail,
    )
    if not result.get('ok'):
        # Intake validation (unknown title, bad payload) — still answer 200
        # so the player never treats telemetry as a playback verdict.
        response = Response({
            'ok': False,
            'error': result.get('error') or 'invalid_payload',
            'problem_type': problem_type,
            'message_fa': 'گزارش خطا ثبت نشد؛ لطفاً از دکمه «گزارش خطا» استفاده کن.',
        })
        response['Cache-Control'] = 'private, no-store'
        return response

    # Fast path: what does the catalog serve *right now* after the inline
    # recheck/queue? A re-signed URL or a gateway-verdict change is often
    # already enough for the player to retry immediately.
    fixed_url = ''
    playback_mode = ''
    try:
        from apps.catalog.models import ContentIssueReport
        from apps.catalog.playback_api import resolve_target

        report = ContentIssueReport.objects.filter(pk=result.get('report_id')).only(
            'content_type', 'object_id', 'episode_id', 'status',
        ).first()
        if report is not None:
            if report.content_type == 'series' and report.episode_id:
                owner, episode = resolve_target('episode', report.episode_id)
            else:
                owner, episode = resolve_target(report.content_type, report.object_id)
            if owner is not None:
                fixed = fixed_playback_for(owner, episode)
                fixed_url = fixed.get('url') or ''
                playback_mode = fixed.get('playback_mode') or ''
                # A stale signed URL that the resolve path just refreshed is
                # the common win: hand the fresh one back even before the
                # worker finishes, when it differs from what failed.
                if fixed_url and fixed_url.strip() != source_url.strip():
                    try:
                        from apps.catalog.playback_resolve import resolve_playback

                        fresh = resolve_playback(owner, episode, allow_refresh=True)
                        if fresh.url and fresh.url.strip() != source_url.strip():
                            fixed_url = fresh.url
                            playback_mode = fresh.mode or playback_mode
                    except Exception:  # noqa: BLE001 — best-effort only
                        pass
    except Exception:  # noqa: BLE001
        pass

    status = str(result.get('status') or 'open')
    resolved = status == 'resolved'
    if resolved and fixed_url and fixed_url.strip() != source_url.strip():
        message_fa = USER_MESSAGES_FA['fixed']
        should_retry = True
    elif resolved:
        message_fa = USER_MESSAGES_FA['already_playable']
        should_retry = bool(fixed_url)
    elif status in {'queued', 'open', 'remediating'}:
        message_fa = USER_MESSAGES_FA['queued']
        should_retry = bool(fixed_url and fixed_url.strip() != source_url.strip())
    elif status == 'needs_review':
        message_fa = USER_MESSAGES_FA['needs_review']
        should_retry = bool(fixed_url and fixed_url.strip() != source_url.strip())
    else:
        message_fa = USER_MESSAGES_FA['unavailable']
        should_retry = bool(fixed_url and fixed_url.strip() != source_url.strip())

    # Watch-party live room: push the outcome to every member so a host-side
    # failure heals guests too, and a guest-side failure still informs the host.
    room_notified = False
    if room_code:
        try:
            from apps.watchparty.playback_notify import notify_room_of_fix

            room_notified = bool(notify_room_of_fix(
                room_code,
                report_id=result.get('report_id'),
                problem_type=problem_type,
                status=status,
                fixed_url=fixed_url,
                playback_mode=playback_mode,
                message_fa=message_fa,
            ))
        except Exception:  # noqa: BLE001 — room notify is best-effort
            room_notified = False

    response = Response({
        'ok': True,
        'report_id': result.get('report_id'),
        'problem_type': problem_type,
        'status': status,
        'report_count': result.get('report_count', 1),
        'auto': True,
        'classification': classification.get('confidence'),
        'fixed_url': fixed_url,
        'playback_mode': playback_mode,
        'should_retry': should_retry,
        'room_notified': room_notified,
        'message_fa': message_fa,
    })
    response['Cache-Control'] = 'private, no-store'
    return response
