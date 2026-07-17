from django.db.models import Q, Count
from decimal import Decimal, InvalidOperation

from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from .models import Actor, Director, Episode, Genre, Movie, Season, Series
from .serializers import (
    ActorListSerializer, DirectorListSerializer, GenreSerializer,
    MovieDetailSerializer, MovieListSerializer, SeriesDetailSerializer,
    SeriesListSerializer,
)


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


def _apply_catalog_filters(queryset, request, year_field):
    query = request.GET.get('q', '').strip()
    year = _bounded_int(request.GET.get('year'), None, 1888, 2100)
    genre = request.GET.get('genre', '').strip()
    country = request.GET.get('country', '').strip()
    language = request.GET.get('language', '').strip()
    age_rating = request.GET.get('age_rating', request.GET.get('age', '')).strip()
    availability = request.GET.get('availability', '').strip()
    content_format = request.GET.get('content_format', '').strip()
    min_rating = _decimal(request.GET.get('min_rating'))

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(original_title__icontains=query)
            | Q(description__icontains=query)
            | Q(actors__name__icontains=query)
            | Q(directors__name__icontains=query)
        )
    if year is not None:
        queryset = queryset.filter(**{year_field: year})
    if genre:
        queryset = queryset.filter(genres__slug=genre)
    if country:
        queryset = queryset.filter(
            Q(countries__code__iexact=country) | Q(countries__name__iexact=country)
        )
    if language:
        queryset = queryset.filter(language__icontains=language)
    if age_rating:
        queryset = queryset.filter(age_rating=age_rating)
    if availability == 'dubbed':
        queryset = queryset.filter(is_dubbed=True)
    elif availability == 'subtitle':
        queryset = queryset.filter(has_subtitle=True)
    if content_format in {'live_action', 'animation', 'short'}:
        queryset = queryset.filter(content_format=content_format)
    if min_rating is not None:
        queryset = queryset.filter(imdb_rating__gte=min_rating)

    return queryset.distinct()


def _catalog_ordering(request, year_field):
    sort = request.GET.get('sort', 'newest')
    if sort == 'rating':
        return [F('imdb_rating').desc(nulls_last=True), F('site_rating').desc(nulls_last=True), '-view_count']
    if sort in {'popular', 'trending'}:
        return ['-view_count', '-like_count', '-created_at']
    return [F(year_field).desc(nulls_last=True), '-created_at']


@api_view(['GET'])
def movie_list(request):
    queryset = _apply_catalog_filters(
        Movie.objects.filter(is_published=True), request, 'release_year',
    ).prefetch_related('genres', 'directors', 'countries').order_by(
        *_catalog_ordering(request, 'release_year')
    )
    paginator = LimitOffsetPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(MovieListSerializer(page, many=True).data)
    return Response(MovieListSerializer(queryset, many=True).data)


@api_view(['GET'])
def movie_detail(request, slug):
    movie = get_object_or_404(
        Movie.objects.filter(is_published=True)
        .prefetch_related('genres', 'movie_actors__actor', 'directors', 'countries', 'tags'),
        slug=slug,
    )
    serializer = MovieDetailSerializer(movie)
    return Response(serializer.data)


@api_view(['GET'])
def series_list(request):
    queryset = Series.objects.filter(is_published=True)
    status = request.GET.get('status')

    if status:
        queryset = queryset.filter(status=status)

    queryset = _apply_catalog_filters(queryset, request, 'start_year').prefetch_related(
        'genres', 'directors', 'countries',
    ).order_by(*_catalog_ordering(request, 'start_year'))
    paginator = LimitOffsetPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(SeriesListSerializer(page, many=True).data)
    return Response(SeriesListSerializer(queryset, many=True).data)


@api_view(['GET'])
def series_detail(request, slug):
    published_episodes = Episode.objects.filter(is_published=True).order_by('episode_number')
    published_seasons = Season.objects.filter(is_published=True).order_by('season_number').prefetch_related(
        Prefetch('episodes', queryset=published_episodes, to_attr='published_episodes'),
    )
    series = get_object_or_404(
        Series.objects.filter(is_published=True)
        .prefetch_related(
            'genres', 'directors', 'countries', 'tags', 'series_actors__actor',
            Prefetch('seasons', queryset=published_seasons, to_attr='published_seasons'),
        ),
        slug=slug,
    )
    serializer = SeriesDetailSerializer(series)
    return Response(serializer.data)


@api_view(['GET'])
def genre_list(request):
    queryset = Genre.objects.all().order_by('title')
    serializer = GenreSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def actor_list(request):
    queryset = Actor.objects.all().order_by('name')
    paginator = LimitOffsetPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(ActorListSerializer(page, many=True).data)
    return Response(ActorListSerializer(queryset, many=True).data)


@api_view(['GET'])
def actor_detail(request, slug):
    actor = get_object_or_404(Actor.objects.all(), slug=slug)
    serializer = ActorListSerializer(actor)
    return Response(serializer.data)


@api_view(['GET'])
def director_list(request):
    queryset = Director.objects.all().order_by('name')
    paginator = LimitOffsetPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(DirectorListSerializer(page, many=True).data)
    return Response(DirectorListSerializer(queryset, many=True).data)


@api_view(['GET'])
def director_detail(request, slug):
    director = get_object_or_404(Director.objects.all(), slug=slug)
    serializer = DirectorListSerializer(director)
    return Response(serializer.data)


@api_view(['GET'])
def search_content(request):
    q = request.GET.get('q', '').strip()
    content_type = request.GET.get('type', 'all')

    if not q:
        return Response({'query': '', 'movies': [], 'series': [], 'actors': []})

    results = {}

    if content_type in ('all', 'movie'):
        movies = Movie.objects.filter(is_published=True).filter(
            Q(title__icontains=q)
            | Q(original_title__icontains=q)
            | Q(description__icontains=q)
            | Q(actors__name__icontains=q)
            | Q(directors__name__icontains=q)
        ).distinct().prefetch_related('genres', 'directors', 'countries')[:10]
        results['movies'] = MovieListSerializer(movies, many=True).data

    if content_type in ('all', 'series'):
        series = Series.objects.filter(is_published=True).filter(
            Q(title__icontains=q)
            | Q(original_title__icontains=q)
            | Q(description__icontains=q)
            | Q(actors__name__icontains=q)
            | Q(directors__name__icontains=q)
        ).distinct().prefetch_related('genres', 'directors', 'countries')[:10]
        results['series'] = SeriesListSerializer(series, many=True).data

    if content_type in ('all', 'actor'):
        actors = Actor.objects.filter(
            Q(name__icontains=q) | Q(biography__icontains=q)
        )[:10]
        results['actors'] = ActorListSerializer(actors, many=True).data

    results['query'] = q
    return Response(results)


@api_view(['GET'])
def trending(request):
    content_type = request.GET.get('type', 'all')
    limit = _bounded_int(request.GET.get('limit'), 20, 1, 50)

    results = {}

    if content_type in ('all', 'movie'):
        movies = Movie.objects.filter(is_published=True).order_by(
            '-view_count', '-like_count', '-created_at'
        ).prefetch_related('genres', 'directors', 'countries')[:limit]
        results['movies'] = MovieListSerializer(movies, many=True).data

    if content_type in ('all', 'series'):
        series = Series.objects.filter(is_published=True).order_by(
            '-view_count', '-like_count', '-created_at'
        ).prefetch_related('genres', 'directors', 'countries')[:limit]
        results['series'] = SeriesListSerializer(series, many=True).data

    return Response(results)
