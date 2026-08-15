#!/usr/bin/env python3
"""Report catalog metadata gaps for movie/series detail pages."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.db.models import Count, Q

from apps.catalog.models import Movie, Series


def movie_gaps(qs, label: str) -> dict:
    data = {
        'total': qs.count(),
        'no_desc': qs.filter(Q(description='') | Q(description__isnull=True)).count(),
        'no_poster': qs.filter(
            (Q(poster='') | Q(poster__isnull=True))
            & (Q(poster_external_url='') | Q(poster_external_url__isnull=True))
            & (Q(poster_path='') | Q(poster_path__isnull=True))
        ).count(),
        'no_backdrop': qs.filter(
            (Q(backdrop='') | Q(backdrop__isnull=True))
            & (Q(backdrop_external_url='') | Q(backdrop_external_url__isnull=True))
            & (Q(backdrop_path='') | Q(backdrop_path__isnull=True))
        ).count(),
        'no_imdb': qs.filter(Q(imdb_id='') | Q(imdb_id__isnull=True)).count(),
        'no_rating': qs.filter(Q(imdb_rating__isnull=True) | Q(imdb_rating=0)).count(),
        'no_trailer': qs.filter(
            (Q(trailer_external_url='') | Q(trailer_external_url__isnull=True))
            & (Q(trailer_url='') | Q(trailer_url__isnull=True))
        ).count(),
        'no_runtime': qs.filter(Q(duration_minutes__isnull=True) | Q(duration_minutes=0)).count(),
        'no_year': qs.filter(
            Q(release_date__isnull=True)
            & (Q(release_year__isnull=True) | Q(release_year=0))
        ).count(),
        'no_genres': qs.annotate(gc=Count('genres')).filter(gc=0).count(),
        'no_dirs': qs.annotate(dc=Count('directors')).filter(dc=0).count(),
        'no_countries': qs.annotate(cc=Count('countries')).filter(cc=0).count(),
        'no_cast': qs.annotate(ac=Count('movie_actors')).filter(ac=0).count(),
        'no_tmdb': qs.filter(tmdb_id__isnull=True).count(),
        'no_links': qs.filter(Q(download_links=[]) | Q(download_links__isnull=True)).count(),
    }
    print(label, data, flush=True)
    return data


def series_gaps(qs, label: str) -> dict:
    data = {
        'total': qs.count(),
        'no_desc': qs.filter(Q(description='') | Q(description__isnull=True)).count(),
        'no_poster': qs.filter(
            (Q(poster='') | Q(poster__isnull=True))
            & (Q(poster_external_url='') | Q(poster_external_url__isnull=True))
        ).count(),
        'no_backdrop': qs.filter(
            (Q(backdrop='') | Q(backdrop__isnull=True))
            & (Q(backdrop_external_url='') | Q(backdrop_external_url__isnull=True))
        ).count(),
        'no_imdb': qs.filter(Q(imdb_id='') | Q(imdb_id__isnull=True)).count(),
        'no_rating': qs.filter(Q(imdb_rating__isnull=True) | Q(imdb_rating=0)).count(),
        'no_trailer': qs.filter(
            (Q(trailer_external_url='') | Q(trailer_external_url__isnull=True))
            & (Q(trailer_url='') | Q(trailer_url__isnull=True))
        ).count(),
        'no_genres': qs.annotate(gc=Count('genres')).filter(gc=0).count(),
        'no_dirs': qs.annotate(dc=Count('directors')).filter(dc=0).count(),
        'no_countries': qs.annotate(cc=Count('countries')).filter(cc=0).count(),
        'no_cast': qs.annotate(ac=Count('series_actors')).filter(ac=0).count(),
        'no_tmdb': qs.filter(tmdb_id__isnull=True).count(),
        'no_links': qs.filter(Q(download_links=[]) | Q(download_links__isnull=True)).count(),
    }
    print(label, data, flush=True)
    return data


movie_gaps(Movie.objects.filter(is_published=True), 'published_movies')
movie_gaps(Movie.objects.all(), 'all_movies')
series_gaps(Series.objects.filter(is_published=True), 'published_series')
series_gaps(Series.objects.all(), 'all_series')
