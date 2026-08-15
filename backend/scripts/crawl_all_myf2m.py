#!/usr/bin/env python3
"""Crawl Film2Media (myf2m) download links for the whole Hollywood catalog.

Goals:
  - Purge Iranian movies/series
  - Fill download_links so online playback works (video_url / episode streams)
  - Queue SoftSub extraction so subtitles sync with the HTML5 player
  - Delete titles that myf2m does not carry

Usage (inside backend container):
  python /app/scripts/crawl_all_myf2m.py --delay 0.55
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# `python /app/scripts/...` puts scripts/ on sys.path[0]; keep /app importable.
_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.iranian import is_iranian_catalog_item
    from apps.catalog.models import Movie, Series
    from apps.catalog.myf2m_reconcile import purge_iranian_catalog
    from apps.catalog.subtitle_extract import download_links_imply_dub, download_links_imply_subtitle
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _link_provider_slug,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
    )
    from apps.catalog.provider_import.registry import get_connector
    from django.conf import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.55)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--limit', type=int, default=0, help='0 = no limit')
    parser.add_argument('--include-complete', action='store_true', help='Also re-crawl titles that already have dub+sub')
    parser.add_argument('--drafts-only', action='store_true')
    parser.add_argument('--no-delete', action='store_true', help='Keep titles even when myf2m misses')
    parser.add_argument('--keep-iranian', action='store_true')
    args = parser.parse_args()

    do_movies = not args.series_only
    do_series = not args.movies_only
    delay = max(0.0, float(args.delay or 0))
    delete_missing = not args.no_delete and bool(
        getattr(settings, 'CATALOG_DELETE_WHEN_PROVIDER_MISSING', True)
    )
    exclude_iranian = not args.keep_iranian and bool(
        getattr(settings, 'CATALOG_EXCLUDE_IRANIAN', True)
    )

    def coverage(obj):
        links = obj.download_links or []
        has_dub = download_links_imply_dub(links)
        has_sub = download_links_imply_subtitle(links)
        return {
            'has_links': _has_download_links(obj),
            'has_dub': has_dub,
            'has_sub': has_sub,
            'has_both': has_dub and has_sub,
        }

    def needs_crawl(obj) -> bool:
        if exclude_iranian and is_iranian_catalog_item(obj):
            return False
        cov = coverage(obj)
        if args.include_complete:
            return True
        if not cov['has_links']:
            return True
        return not cov['has_both']

    def priority(obj) -> tuple:
        cov = coverage(obj)
        return (
            0 if not cov['has_links'] else 1,
            0 if not cov['has_both'] else 1,
            -(float(getattr(obj, 'popularity', 0) or 0)),
            -(int(getattr(obj, 'id', 0) or 0)),
        )

    # Always force myf2m for this script.
    provider = 'myf2m'
    print(f'provider={provider} (settings={_link_provider_slug()})', flush=True)

    stats = {
        'iranian_movies_deleted': 0,
        'iranian_series_deleted': 0,
        'movies_tried': 0,
        'movies_ok': 0,
        'movies_both': 0,
        'movies_published': 0,
        'movies_deleted': 0,
        'series_tried': 0,
        'series_ok': 0,
        'series_both': 0,
        'series_published': 0,
        'series_deleted': 0,
        'failed': 0,
    }

    if exclude_iranian:
        purged = purge_iranian_catalog(dry_run=False)
        stats['iranian_movies_deleted'] = purged['iranian_movies_deleted']
        stats['iranian_series_deleted'] = purged['iranian_series_deleted']
        print(
            f'purged iranian movies={purged["iranian_movies_deleted"]} '
            f'series={purged["iranian_series_deleted"]}',
            flush=True,
        )

    connector = get_connector(provider)
    connector.authenticate()

    try:
        with _suppress_provider_publish_signals():
            if do_movies:
                qs = Movie.objects.all() if not args.drafts_only else Movie.objects.filter(is_published=False)
                movies = [m for m in qs.iterator(chunk_size=200) if needs_crawl(m)]
                movies.sort(key=priority)
                if args.limit:
                    movies = movies[: args.limit]
                print(f'crawl movies={len(movies)}', flush=True)
                for movie in movies:
                    stats['movies_tried'] += 1
                    before = coverage(movie)
                    print(
                        f'[movie {stats["movies_tried"]}/{len(movies)}] '
                        f'{movie.title} links={before["has_links"]} both={before["has_both"]}',
                        flush=True,
                    )
                    result = _crawl_movie_links(movie, connector, replace=True)
                    movie.refresh_from_db()
                    after = coverage(movie)
                    status = result.get('status')
                    count = result.get('imported_count', 0)
                    if status == 'ok' and count:
                        stats['movies_ok'] += 1
                    elif delete_missing and (
                        status == 'page_not_found'
                        or result.get('code') in {'myf2m_page_required', 'myf2m_links_empty'}
                        or (status == 'ok' and not after['has_links'])
                    ):
                        print('  -> deleted (missing on myf2m)', flush=True)
                        movie.delete()
                        stats['movies_deleted'] += 1
                        if delay:
                            time.sleep(delay)
                        continue
                    else:
                        stats['failed'] += 1
                    if after['has_both']:
                        stats['movies_both'] += 1
                    if after['has_links'] and not movie.is_published:
                        if _publish_movie(movie):
                            stats['movies_published'] += 1
                            print('  -> published', flush=True)
                    print(
                        f'  -> {status} imported={count} '
                        f'dub={after["has_dub"]} sub={after["has_sub"]} both={after["has_both"]} '
                        f'video={bool(movie.video_url)}',
                        flush=True,
                    )
                    if delay:
                        time.sleep(delay)

            if do_series:
                qs = Series.objects.all() if not args.drafts_only else Series.objects.filter(is_published=False)
                series_rows = [s for s in qs.iterator(chunk_size=200) if needs_crawl(s)]
                series_rows.sort(key=priority)
                if args.limit:
                    series_rows = series_rows[: args.limit]
                print(f'crawl series={len(series_rows)}', flush=True)
                for series in series_rows:
                    stats['series_tried'] += 1
                    before = coverage(series)
                    print(
                        f'[series {stats["series_tried"]}/{len(series_rows)}] '
                        f'{series.title} links={before["has_links"]} both={before["has_both"]}',
                        flush=True,
                    )
                    result = _crawl_series_links(series, connector, replace=True)
                    series.refresh_from_db()
                    after = coverage(series)
                    status = result.get('status')
                    count = result.get('imported_count', 0)
                    if status == 'ok' and count:
                        stats['series_ok'] += 1
                    elif delete_missing and (
                        status == 'page_not_found'
                        or result.get('code') in {'myf2m_page_required', 'myf2m_links_empty'}
                        or (status == 'ok' and not after['has_links'])
                    ):
                        print('  -> deleted (missing on myf2m)', flush=True)
                        series.delete()
                        stats['series_deleted'] += 1
                        if delay:
                            time.sleep(delay)
                        continue
                    else:
                        stats['failed'] += 1
                    if after['has_both']:
                        stats['series_both'] += 1
                    if after['has_links'] and not series.is_published:
                        if _publish_series(series):
                            stats['series_published'] += 1
                            print('  -> published', flush=True)
                    print(
                        f'  -> {status} imported={count} '
                        f'dub={after["has_dub"]} sub={after["has_sub"]} both={after["has_both"]}',
                        flush=True,
                    )
                    if delay:
                        time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    print('CRAWL_ALL_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
