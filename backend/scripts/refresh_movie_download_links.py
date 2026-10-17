#!/usr/bin/env python3
"""Refresh published movies so newly released Film2Media qualities appear.

Re-crawls the Film2Media page recorded on each movie's download links and
coalesces any quality/dub/hardsub/SoftSub encode we do not have yet. Matching
CDN paths refresh signed URLs; existing rows are never wiped by a partial
crawl. Movies are selected oldest-refresh-first so every title is revisited
within a bounded number of rounds, with an optional popularity/recent-year
priority pass for titles most likely to gain new encodes.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def _page_path(movie) -> str:
    for item in movie.download_links or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get('page_path') or '').strip()
        if path.startswith('/') and '/series/' not in path:
            return path
    return ''


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.utils import timezone

    from apps.catalog.models import Movie
    from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_movie
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.refresh_rotation import (
        forget_failure,
        is_rotating_failure,
        recently_failed,
        remember_failure,
    )
    from apps.catalog.top_catalog import _has_download_links, _suppress_provider_publish_signals

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.7)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--popularity-min', type=float, default=0.0)
    parser.add_argument(
        '--year-min',
        type=int,
        default=0,
        help='Only movies whose release_year is >= this (e.g. 2024 for recent releases)',
    )
    parser.add_argument(
        '--order',
        choices=('hot', 'stale', 'popular'),
        default='hot',
        help=(
            'hot = this week\'s trending + recent releases first (capped, rested), then '
            'stale rotation; stale = least-recently-updated first (full coverage); '
            'popular = -popularity first'
        ),
    )
    args = parser.parse_args()
    workers = max(1, min(8, int(args.workers)))
    request_interval = max(0.0, float(args.delay))

    qs = (
        Movie.objects.filter(is_published=True)
        .exclude(download_links=[])
        .exclude(download_links__isnull=True)
    )
    if args.order == 'popular':
        qs = qs.order_by('-popularity', '-updated_at', '-id')
    else:
        qs = qs.order_by('updated_at', '-popularity', '-id')

    movie_rows = [m for m in qs.iterator(chunk_size=100) if _page_path(m) and _has_download_links(m)]
    if args.year_min:
        year_min = int(args.year_min)
        movie_rows = [m for m in movie_rows if int(m.release_year or 0) >= year_min]
    if args.popularity_min:
        movie_rows = [m for m in movie_rows if float(m.popularity or 0) >= args.popularity_min]
    # Titles the provider just refused are skipped for a while, otherwise the
    # same taken-down titles fill the whole slice every round.
    resting = recently_failed('movie', [m.pk for m in movie_rows])
    if resting:
        movie_rows = [m for m in movie_rows if m.pk not in resting]
    if args.order == 'hot':
        from apps.catalog.hot_titles import hot_head

        movie_rows = hot_head(movie_rows, 'movie', limit=args.limit or len(movie_rows))
    if args.limit:
        movie_rows = movie_rows[: max(1, args.limit)]

    stats = {
        'tried': 0,
        'ok': 0,
        'failed': 0,
        'links_before_total': sum(len(m.download_links or []) for m in movie_rows),
        'grew': 0,
    }
    print(
        f'refresh_movies={len(movie_rows)} order={args.order} resting={len(resting)} '
        f'workers={workers}',
        flush=True,
    )

    # Same bounded-parallel pattern as the series refresh: network waits
    # overlap across workers while pace_lock keeps one shared request cadence,
    # so the provider sees the same polite rate as a sequential walk.
    pace_lock = threading.Lock()
    next_request_at = [0.0]

    def refresh_one(movie_id: int, page: str):
        from django.db import close_old_connections

        close_old_connections()
        with pace_lock:
            wait = next_request_at[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            next_request_at[0] = time.monotonic() + request_interval
        try:
            movie = Movie.objects.get(pk=movie_id)
            before = len(movie.download_links or [])
            result = crawl_myf2m_downloads_for_movie(
                movie=movie,
                page_url=page,
                replace=True,
                queue_softsub_extract=True,
            )
            movie.refresh_from_db(fields=['download_links', 'updated_at', 'has_subtitle', 'is_dubbed'])
            after = len(movie.download_links or [])
            forget_failure('movie', movie_id)
            return 'ok', result.get('imported_count') or after, before, after
        except ProviderImportError as exc:
            if is_rotating_failure(exc):
                remember_failure('movie', movie_id)
            return 'fail', getattr(exc, 'code', ''), str(exc), 0
        except Exception as exc:
            return 'error', type(exc).__name__, str(exc), 0
        finally:
            close_old_connections()

    with _suppress_provider_publish_signals():
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='movie-refresh') as pool:
            pending = {
                pool.submit(refresh_one, movie.pk, _page_path(movie)): movie
                for movie in movie_rows
            }
            for future in as_completed(pending):
                movie = pending[future]
                stats['tried'] += 1
                status, first, second, after = future.result()
                if status == 'ok':
                    before = int(second)
                    stats['ok'] += 1
                    if int(after) > before:
                        stats['grew'] += 1
                    print(
                        f'[{stats["tried"]}/{len(movie_rows)}] ok movie={movie.pk} '
                        f'{movie.title} links {before}->{after} imported={first}',
                        flush=True,
                    )
                else:
                    stats['failed'] += 1
                    print(
                        f'[{stats["tried"]}/{len(movie_rows)}] {status} movie={movie.pk} '
                        f'{movie.title} {first} {second}',
                        flush=True,
                    )

    stats['finished_at'] = timezone.now().isoformat()
    print('REFRESH_MOVIES_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
