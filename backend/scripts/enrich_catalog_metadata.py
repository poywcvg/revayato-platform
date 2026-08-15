#!/usr/bin/env python3
"""Re-sync incomplete movie/series metadata from TMDB for full detail pages.

Fills description, artwork, cast, directors, countries, genres, runtime,
trailer, IMDb id/rating hooks, etc. via upsert_tmdb_*.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db.models import Count, Q

    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.models import Movie, Series
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument(
        '--year',
        type=int,
        default=0,
        help='Only enrich titles from this release/start year.',
    )
    parser.add_argument('--sleep', type=float, default=0.2)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--published-only', action='store_true', default=True)
    parser.add_argument('--include-unpublished', action='store_false', dest='published_only')
    parser.add_argument(
        '--force-all',
        action='store_true',
        help='Re-sync every title with a tmdb_id (not only incomplete ones).',
    )
    args = parser.parse_args()

    client = configured_tmdb_client()
    limit = max(0, int(args.limit or 0))
    sleep = max(0.0, float(args.sleep or 0))
    do_movies = not args.series_only
    do_series = not args.movies_only

    stats = {
        'movies_tried': 0,
        'movies_ok': 0,
        'series_tried': 0,
        'series_ok': 0,
        'errors': 0,
        'skipped_no_tmdb': 0,
    }

    def movie_incomplete(qs):
        if args.force_all:
            return qs.exclude(tmdb_id__isnull=True)
        missing_poster = (
            (Q(poster='') | Q(poster__isnull=True))
            & (Q(poster_external_url='') | Q(poster_external_url__isnull=True))
            & (Q(poster_path='') | Q(poster_path__isnull=True))
        )
        missing_backdrop = (
            (Q(backdrop='') | Q(backdrop__isnull=True))
            & (Q(backdrop_external_url='') | Q(backdrop_external_url__isnull=True))
            & (Q(backdrop_path='') | Q(backdrop_path__isnull=True))
        )
        missing_trailer = (
            (Q(trailer_external_url='') | Q(trailer_external_url__isnull=True))
            & (Q(trailer_url='') | Q(trailer_url__isnull=True))
        )
        return qs.exclude(tmdb_id__isnull=True).annotate(
            gc=Count('genres', distinct=True),
            dc=Count('directors', distinct=True),
            cc=Count('countries', distinct=True),
            ac=Count('movie_actors', distinct=True),
        ).filter(
            Q(description='') | Q(description__isnull=True)
            | missing_poster
            | missing_backdrop
            | Q(imdb_id='') | Q(imdb_id__isnull=True)
            | Q(imdb_rating__isnull=True) | Q(imdb_rating=0)
            | missing_trailer
            | Q(duration_minutes__isnull=True) | Q(duration_minutes=0)
            | Q(release_date__isnull=True)
            | Q(gc=0) | Q(dc=0) | Q(cc=0) | Q(ac=0)
        )

    def series_incomplete(qs):
        if args.force_all:
            return qs.exclude(tmdb_id__isnull=True)
        missing_poster = (
            (Q(poster='') | Q(poster__isnull=True))
            & (Q(poster_external_url='') | Q(poster_external_url__isnull=True))
        )
        missing_backdrop = (
            (Q(backdrop='') | Q(backdrop__isnull=True))
            & (Q(backdrop_external_url='') | Q(backdrop_external_url__isnull=True))
        )
        missing_trailer = (
            (Q(trailer_external_url='') | Q(trailer_external_url__isnull=True))
            & (Q(trailer_url='') | Q(trailer_url__isnull=True))
        )
        return qs.exclude(tmdb_id__isnull=True).annotate(
            gc=Count('genres', distinct=True),
            dc=Count('directors', distinct=True),
            cc=Count('countries', distinct=True),
            ac=Count('series_actors', distinct=True),
        ).filter(
            Q(description='') | Q(description__isnull=True)
            | missing_poster
            | missing_backdrop
            | Q(imdb_id='') | Q(imdb_id__isnull=True)
            | Q(imdb_rating__isnull=True) | Q(imdb_rating=0)
            | missing_trailer
            | Q(gc=0) | Q(dc=0) | Q(cc=0) | Q(ac=0)
        )

    if do_movies:
        mqs = Movie.objects.all()
        if args.year:
            mqs = mqs.filter(release_year=args.year)
        if args.published_only:
            mqs = mqs.filter(is_published=True)
        movies = list(movie_incomplete(mqs).order_by('-popularity', '-id'))
        if limit:
            movies = movies[:limit]
        print(f'enrich movies={len(movies)}', flush=True)
        for idx, movie in enumerate(movies, 1):
            stats['movies_tried'] += 1
            if not movie.tmdb_id:
                stats['skipped_no_tmdb'] += 1
                continue
            try:
                details = client.movie_details(int(movie.tmdb_id))
                upsert_tmdb_movie(details, auto_publish=False, overwrite_manual=False)
                stats['movies_ok'] += 1
                if idx % 25 == 0 or idx == 1:
                    print(
                        f'[movie {idx}/{len(movies)}] id={movie.pk} tmdb={movie.tmdb_id} {movie.title}',
                        flush=True,
                    )
            except TMDBError as exc:
                stats['errors'] += 1
                print(f'  movie#{movie.pk} tmdb error: {exc}', flush=True)
            except Exception as exc:
                stats['errors'] += 1
                print(f'  movie#{movie.pk} error {type(exc).__name__}: {exc}', flush=True)
            if sleep:
                time.sleep(sleep)

    if do_series:
        sqs = Series.objects.all()
        if args.year:
            sqs = sqs.filter(start_year=args.year)
        if args.published_only:
            sqs = sqs.filter(is_published=True)
        series_rows = list(series_incomplete(sqs).order_by('-popularity', '-id'))
        # series limit shares remaining budget if movies already ran with --limit
        if limit and do_movies:
            remain = max(0, limit - stats['movies_tried'])
            series_rows = series_rows[:remain]
        elif limit:
            series_rows = series_rows[:limit]
        print(f'enrich series={len(series_rows)}', flush=True)
        for idx, series in enumerate(series_rows, 1):
            stats['series_tried'] += 1
            if not series.tmdb_id:
                stats['skipped_no_tmdb'] += 1
                continue
            try:
                details = client.tv_details(int(series.tmdb_id))
                upsert_tmdb_series(details)
                stats['series_ok'] += 1
                if idx % 25 == 0 or idx == 1:
                    print(
                        f'[series {idx}/{len(series_rows)}] id={series.pk} tmdb={series.tmdb_id} {series.title}',
                        flush=True,
                    )
            except TMDBError as exc:
                stats['errors'] += 1
                print(f'  series#{series.pk} tmdb error: {exc}', flush=True)
            except Exception as exc:
                stats['errors'] += 1
                print(f'  series#{series.pk} error {type(exc).__name__}: {exc}', flush=True)
            if sleep:
                time.sleep(sleep)

    print('ENRICH_METADATA_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
