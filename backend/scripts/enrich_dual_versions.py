#!/usr/bin/env python3
"""Re-crawl published titles that are missing Persian dub or subtitle encodes.

Goal: maximize titles where the player can offer both «دوبله» and «زیرنویس».
Run inside the backend container:

  python /app/scripts/enrich_dual_versions.py --limit 200 --delay 0.6
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


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.models import Movie, Series
    from apps.catalog.subtitle_extract import download_links_imply_dub, download_links_imply_subtitle
    from apps.catalog.top_catalog import _crawl_movie_links, _crawl_series_links, _link_provider_slug
    from apps.catalog.provider_import.registry import get_connector

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--delay', type=float, default=0.6)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    args = parser.parse_args()

    do_movies = not args.series_only
    do_series = not args.movies_only

    def incomplete(obj) -> bool:
        links = obj.download_links or []
        has_dub = download_links_imply_dub(links)
        has_sub = download_links_imply_subtitle(links)
        return not (has_dub and has_sub)

    connector = get_connector(_link_provider_slug())
    connector.authenticate()

    stats = {'movies': 0, 'movies_ok': 0, 'series': 0, 'series_ok': 0, 'both_after': 0}

    try:
        if do_movies:
            movies = [
                m for m in Movie.objects.filter(is_published=True).order_by('-popularity', '-id')[: args.limit * 3]
                if incomplete(m)
            ][: args.limit]
            for movie in movies:
                stats['movies'] += 1
                print(f'[movie] {movie.title}', flush=True)
                result = _crawl_movie_links(movie, connector, replace=True)
                movie.refresh_from_db()
                if result.get('status') == 'ok':
                    stats['movies_ok'] += 1
                if not incomplete(movie):
                    stats['both_after'] += 1
                    print(f'  -> both versions ready ({result.get("imported_count", 0)} links)', flush=True)
                else:
                    print(f'  -> {result.get("status")} (still incomplete)', flush=True)
                if args.delay > 0:
                    time.sleep(args.delay)

        if do_series:
            series_rows = [
                s for s in Series.objects.filter(is_published=True).order_by('-popularity', '-id')[: args.limit * 3]
                if incomplete(s)
            ][: args.limit]
            for series in series_rows:
                stats['series'] += 1
                print(f'[series] {series.title}', flush=True)
                result = _crawl_series_links(series, connector, replace=True)
                series.refresh_from_db()
                if result.get('status') == 'ok':
                    stats['series_ok'] += 1
                if not incomplete(series):
                    stats['both_after'] += 1
                    print(f'  -> both versions ready ({result.get("imported_count", 0)} links)', flush=True)
                else:
                    print(f'  -> {result.get("status")} (still incomplete)', flush=True)
                if args.delay > 0:
                    time.sleep(args.delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    print('DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
