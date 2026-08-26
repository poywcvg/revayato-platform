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
import time
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
    from apps.catalog.top_catalog import _has_download_links, _suppress_provider_publish_signals

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.7)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--popularity-min', type=float, default=0.0)
    parser.add_argument(
        '--year-min',
        type=int,
        default=0,
        help='Only movies whose release_year is >= this (e.g. 2024 for recent releases)',
    )
    parser.add_argument(
        '--order',
        choices=('stale', 'popular'),
        default='stale',
        help='stale = least-recently-updated first (full coverage); popular = -popularity first',
    )
    args = parser.parse_args()

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
    if args.limit:
        movie_rows = movie_rows[: max(1, args.limit)]

    stats = {
        'tried': 0,
        'ok': 0,
        'failed': 0,
        'links_before_total': sum(len(m.download_links or []) for m in movie_rows),
        'grew': 0,
    }
    print(f'refresh_movies={len(movie_rows)} order={args.order}', flush=True)

    with _suppress_provider_publish_signals():
        for movie in movie_rows:
            stats['tried'] += 1
            page = _page_path(movie)
            before = len(movie.download_links or [])
            print(f'[{stats["tried"]}/{len(movie_rows)}] movie={movie.pk} {movie.title} page={page}', flush=True)
            try:
                result = crawl_myf2m_downloads_for_movie(
                    movie=movie,
                    page_url=page,
                    replace=True,
                    queue_softsub_extract=True,
                )
                movie.refresh_from_db(fields=['download_links', 'updated_at', 'has_subtitle', 'is_dubbed'])
                after = len(movie.download_links or [])
                stats['ok'] += 1
                if after > before:
                    stats['grew'] += 1
                print(
                    f'  -> ok imported={result.get("imported_count")} links {before}->{after}',
                    flush=True,
                )
            except ProviderImportError as exc:
                stats['failed'] += 1
                print(f'  -> fail {getattr(exc, "code", "")} {exc}', flush=True)
            except Exception as exc:
                stats['failed'] += 1
                print(f'  -> error {type(exc).__name__}: {exc}', flush=True)
            if args.delay:
                time.sleep(max(0.0, float(args.delay)))

    stats['finished_at'] = timezone.now().isoformat()
    print('REFRESH_MOVIES_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
