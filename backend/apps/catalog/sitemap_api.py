"""Compact, cached feed of every indexable URL for the web sitemap.

    GET /api/catalog/sitemap/                       summary: counts + landing facets
    GET /api/catalog/sitemap/?kind=movies&page=1    one sitemap part (slug, lastmod, image, title)

Only published titles (and actors who appear in one) are listed, so the sitemap
never advertises a page that answers 404. Landing facets (genre / country /
year) are listed only when they hold enough titles to be a real page rather
than a thin one.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Exists, OuterRef, Q
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from config.public_urls import media_url

from .models import Actor, Country, Genre, Movie, MovieActor, Series, SeriesActor

PAGE_SIZE = 5000
#: A landing page with fewer titles than this is thin content; keep it out.
MIN_LANDING_TITLES = 8
_TTL = 3 * 60 * 60


class SitemapThrottle(AnonRateThrottle):
    scope = 'catalog'


def _image(obj, field='poster'):
    value = getattr(obj, field, None)
    if getattr(value, 'name', None):
        url = media_url(value) or ''
        if url.startswith(('http://', 'https://')):
            return url
        # No CDN base: media_url is site-relative ("/media/..."). A sitemap
        # image must be absolute, so anchor it on the site host.
        site = (getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')
        if url.startswith('/') and site:
            return f'{site}{url}'
    return (getattr(obj, f'{field}_external_url', '') or '').strip()


def _published_actors():
    return Actor.objects.filter(
        Exists(MovieActor.objects.filter(actor=OuterRef('pk'), movie__is_published=True))
        | Exists(SeriesActor.objects.filter(actor=OuterRef('pk'), series__is_published=True))
    )


def _summary():
    movies = Movie.objects.filter(is_published=True)
    series = Series.objects.filter(is_published=True)

    def facet(model_qs, field):
        return {
            row[field]: row['n']
            for row in model_qs.exclude(**{f'{field}__isnull': True}).values(field).annotate(n=Count('pk', distinct=True))
            if row[field] and row['n'] >= MIN_LANDING_TITLES
        }

    genre_movies = facet(movies, 'genres__slug')
    genre_series = facet(series, 'genres__slug')
    country_movies = facet(movies, 'countries__code')
    country_series = facet(series, 'countries__code')
    year_movies = facet(movies, 'release_year')
    year_series = facet(series, 'start_year')
    return {
        'page_size': PAGE_SIZE,
        'counts': {
            'movies': movies.count(),
            'series': series.count(),
            'actors': _published_actors().count(),
        },
        'genres': [
            {'slug': slug, 'movies': genre_movies.get(slug, 0), 'series': genre_series.get(slug, 0)}
            for slug in Genre.objects.filter(slug__in={*genre_movies, *genre_series}).values_list('slug', flat=True)
        ],
        'countries': [
            {'code': code.upper(), 'movies': country_movies.get(code, 0), 'series': country_series.get(code, 0)}
            for code in Country.objects.filter(code__in={*country_movies, *country_series}).values_list('code', flat=True)
        ],
        'years': {
            'movies': sorted(year_movies, reverse=True),
            'series': sorted(year_series, reverse=True),
        },
    }


def _part(kind, page):
    offset = (page - 1) * PAGE_SIZE
    rows = []
    if kind in {'movies', 'series'}:
        model = Movie if kind == 'movies' else Series
        qs = (
            model.objects.filter(is_published=True)
            .only('id', 'slug', 'title', 'updated_at', 'poster', 'poster_external_url')
            .order_by('id')[offset:offset + PAGE_SIZE]
        )
        for obj in qs:
            rows.append({
                'slug': obj.slug,
                'lastmod': obj.updated_at.isoformat() if obj.updated_at else '',
                'image': _image(obj),
                'title': obj.title,
            })
    elif kind == 'actors':
        qs = (
            _published_actors()
            .only('id', 'slug', 'name', 'updated_at', 'photo', 'photo_external_url')
            .order_by('id')[offset:offset + PAGE_SIZE]
        )
        for obj in qs:
            rows.append({
                'slug': obj.slug,
                'lastmod': obj.updated_at.isoformat() if obj.updated_at else '',
                'image': _image(obj, 'photo'),
                'title': obj.name,
            })
    return {'kind': kind, 'page': page, 'results': rows}


@api_view(['GET'])
@throttle_classes([SitemapThrottle])
def catalog_sitemap(request):
    kind = (request.GET.get('kind') or '').strip()
    if kind and kind not in {'movies', 'series', 'actors'}:
        return Response({'detail': 'unknown kind'}, status=400)
    try:
        page = max(1, min(int(request.GET.get('page') or 1), 1000))
    except (TypeError, ValueError):
        page = 1
    # Not tied to the catalog cache version: that bumps on every edit, and the
    # sitemap is re-read by crawlers on their own (hours-long) schedule.
    key = f'catalog:sitemap:{kind or "summary"}:{page}'
    payload = cache.get(key)
    if payload is None:
        payload = _part(kind, page) if kind else _summary()
        cache.set(key, payload, timeout=_TTL)
    response = Response(payload)
    response['Cache-Control'] = 'public, max-age=900'
    return response
