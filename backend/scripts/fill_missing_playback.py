#!/usr/bin/env python3
"""Fill missing download/playback links + refresh incomplete TMDB metadata.

Usage (backend container):
  PYTHONPATH=/app python /app/scripts/fill_missing_playback.py --delay 0.8
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.models import Movie, Series
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import (
        download_links_imply_dub,
        download_links_imply_subtitle,
        ensure_episodes_from_download_links,
    )
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _link_provider_slug,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
    )
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.75)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--skip-metadata', action='store_true')
    parser.add_argument('--skip-crawl', action='store_true')
    parser.add_argument('--metadata-only-gaps', action='store_true', help='Only re-sync incomplete metadata')
    args = parser.parse_args()

    delay = max(0.0, float(args.delay or 0))
    do_movies = not args.series_only
    do_series = not args.movies_only

    stats = {
        'meta_movies': 0,
        'meta_series': 0,
        'meta_errors': 0,
        'movies_tried': 0,
        'movies_ok': 0,
        'movies_both': 0,
        'movies_published': 0,
        'series_tried': 0,
        'series_ok': 0,
        'series_both': 0,
        'series_published': 0,
        'failed': 0,
        'episodes_synced': 0,
    }

    def incomplete_meta_movie(movie: Movie) -> bool:
        if not (movie.description or '').strip() and not (movie.short_description or '').strip():
            return True
        if not movie.poster:
            return True
        if not movie.genres.exists():
            return True
        if not movie.actors.exists():
            return True
        if not movie.directors.exists():
            return True
        return False

    def incomplete_meta_series(series: Series) -> bool:
        if not (series.description or '').strip() and not (series.short_description or '').strip():
            return True
        if not series.poster:
            return True
        if not series.genres.exists():
            return True
        if not series.actors.exists():
            return True
        return False

    def coverage(obj):
        links = obj.download_links or []
        return {
            'has_links': _has_download_links(obj),
            'has_dub': download_links_imply_dub(links),
            'has_sub': download_links_imply_subtitle(links),
            'has_both': download_links_imply_dub(links) and download_links_imply_subtitle(links),
        }

    # --- Metadata refresh ---
    if not args.skip_metadata:
        try:
            client = configured_tmdb_client()
        except Exception as exc:
            print(f'TMDB unavailable: {exc}', flush=True)
            client = None
        if client is not None:
            if do_movies:
                qs = Movie.objects.exclude(tmdb_id__isnull=True).order_by('-popularity', '-id')
                if args.metadata_only_gaps:
                    movies_meta = [m for m in qs.iterator(chunk_size=100) if incomplete_meta_movie(m)]
                else:
                    # Still prioritize gaps, then a popular sweep.
                    gaps = [m for m in qs.iterator(chunk_size=100) if incomplete_meta_movie(m)]
                    popular = list(qs.filter(is_published=True)[:120])
                    seen = {m.id for m in gaps}
                    movies_meta = gaps + [m for m in popular if m.id not in seen]
                if args.limit:
                    movies_meta = movies_meta[: args.limit]
                print(f'metadata movies={len(movies_meta)}', flush=True)
                for i, movie in enumerate(movies_meta, 1):
                    try:
                        details = client.movie_details(movie.tmdb_id)
                        upsert_tmdb_movie(details, overwrite_manual=False)
                        stats['meta_movies'] += 1
                        print(f'[meta movie {i}/{len(movies_meta)}] {movie.title} ok', flush=True)
                    except TMDBError as exc:
                        stats['meta_errors'] += 1
                        print(f'[meta movie {i}] {movie.title} err {exc}', flush=True)
                    except Exception as exc:
                        stats['meta_errors'] += 1
                        print(f'[meta movie {i}] {movie.title} err {exc}', flush=True)
                    if delay:
                        time.sleep(min(delay, 0.35))
            if do_series:
                qs = Series.objects.exclude(tmdb_id__isnull=True).order_by('-popularity', '-id')
                if args.metadata_only_gaps:
                    series_meta = [s for s in qs.iterator(chunk_size=100) if incomplete_meta_series(s)]
                else:
                    gaps = [s for s in qs.iterator(chunk_size=100) if incomplete_meta_series(s)]
                    popular = list(qs.filter(is_published=True)[:80])
                    seen = {s.id for s in gaps}
                    series_meta = gaps + [s for s in popular if s.id not in seen]
                if args.limit:
                    series_meta = series_meta[: args.limit]
                print(f'metadata series={len(series_meta)}', flush=True)
                for i, series in enumerate(series_meta, 1):
                    try:
                        details = client.tv_details(series.tmdb_id)
                        upsert_tmdb_series(details)
                        stats['meta_series'] += 1
                        print(f'[meta series {i}/{len(series_meta)}] {series.title} ok', flush=True)
                    except TMDBError as exc:
                        stats['meta_errors'] += 1
                        print(f'[meta series {i}] {series.title} err {exc}', flush=True)
                    except Exception as exc:
                        stats['meta_errors'] += 1
                        print(f'[meta series {i}] {series.title} err {exc}', flush=True)
                    if delay:
                        time.sleep(min(delay, 0.35))

    if args.skip_crawl:
        print('FILL_DONE', stats, flush=True)
        return 0

    # --- Download / playback crawl ---
    provider = _link_provider_slug()
    print(f'provider={provider}', flush=True)
    connector = get_connector(provider)
    connector.authenticate()

    try:
        with _suppress_provider_publish_signals():
            if do_movies:
                movies = [
                    m for m in Movie.objects.filter(is_published=True).order_by('-popularity', '-id')
                    if not _has_download_links(m)
                ]
                # Also refresh incomplete dual for popular titles.
                incomplete = [
                    m for m in Movie.objects.filter(is_published=True).order_by('-popularity', '-id')[:250]
                    if _has_download_links(m) and not coverage(m)['has_both']
                ]
                # Missing first, then dual-incomplete.
                seen = set()
                ordered = []
                for m in movies + incomplete:
                    if m.id in seen:
                        continue
                    seen.add(m.id)
                    ordered.append(m)
                if args.limit:
                    ordered = ordered[: args.limit]
                print(f'crawl movies={len(ordered)}', flush=True)
                for i, movie in enumerate(ordered, 1):
                    stats['movies_tried'] += 1
                    before = coverage(movie)
                    print(
                        f'[movie {i}/{len(ordered)}] {movie.original_title or movie.title} '
                        f'({movie.release_year}) links={before["has_links"]} both={before["has_both"]}',
                        flush=True,
                    )
                    result = _crawl_movie_links(movie, connector, replace=True)
                    movie.refresh_from_db()
                    after = coverage(movie)
                    status = result.get('status')
                    count = result.get('imported_count', 0)
                    if status == 'ok' and count:
                        stats['movies_ok'] += 1
                    else:
                        stats['failed'] += 1
                    if after['has_both']:
                        stats['movies_both'] += 1
                    if after['has_links'] and not movie.is_published:
                        if _publish_movie(movie):
                            stats['movies_published'] += 1
                    print(
                        f'  -> {status} imported={count} dub={after["has_dub"]} '
                        f'sub={after["has_sub"]} both={after["has_both"]} video={bool(movie.video_url)}',
                        flush=True,
                    )
                    if delay:
                        time.sleep(delay)

            if do_series:
                series_rows = [
                    s for s in Series.objects.filter(is_published=True).order_by('-popularity', '-id')
                    if not _has_download_links(s)
                ]
                incomplete = [
                    s for s in Series.objects.filter(is_published=True).order_by('-popularity', '-id')[:150]
                    if _has_download_links(s) and not coverage(s)['has_both']
                ]
                seen = set()
                ordered = []
                for s in series_rows + incomplete:
                    if s.id in seen:
                        continue
                    seen.add(s.id)
                    ordered.append(s)
                if args.limit:
                    ordered = ordered[: args.limit]
                print(f'crawl series={len(ordered)}', flush=True)
                for i, series in enumerate(ordered, 1):
                    stats['series_tried'] += 1
                    before = coverage(series)
                    print(
                        f'[series {i}/{len(ordered)}] {series.original_title or series.title} '
                        f'({series.start_year}) links={before["has_links"]} both={before["has_both"]}',
                        flush=True,
                    )
                    result = _crawl_series_links(series, connector, replace=True)
                    series.refresh_from_db()
                    after = coverage(series)
                    status = result.get('status')
                    count = result.get('imported_count', 0)
                    if status == 'ok' and count:
                        stats['series_ok'] += 1
                        try:
                            stats['episodes_synced'] += ensure_episodes_from_download_links(series)
                        except Exception as exc:
                            print(f'  episode sync err: {exc}', flush=True)
                    else:
                        stats['failed'] += 1
                    if after['has_both']:
                        stats['series_both'] += 1
                    if after['has_links'] and not series.is_published:
                        if _publish_series(series):
                            stats['series_published'] += 1
                    print(
                        f'  -> {status} imported={count} dub={after["has_dub"]} '
                        f'sub={after["has_sub"]} both={after["has_both"]}',
                        flush=True,
                    )
                    if delay:
                        time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    print('FILL_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
