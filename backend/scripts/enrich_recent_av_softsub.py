#!/usr/bin/env python3
"""Re-crawl recently added titles for dub+sub links and queue SoftSub WebVTT."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.utils import timezone

    from apps.catalog.models import Movie, Series
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        download_links_imply_dub,
        download_links_imply_subtitle,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.top_catalog import _crawl_movie_links, _crawl_series_links, _link_provider_slug

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=float(os.environ.get('ENRICH_HOURS', '18') or 18))
    parser.add_argument('--delay', type=float, default=float(os.environ.get('ENRICH_DELAY', '0.55') or 0.55))
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    # Support `python - < script.py` (stdin) where argv is just ['-'].
    args = parser.parse_args([] if len(sys.argv) <= 1 or sys.argv[0] == '-' else None)

    since = timezone.now() - timedelta(hours=max(1.0, float(args.hours)))
    delay = max(0.0, float(args.delay))
    do_movies = not args.series_only
    do_series = not args.movies_only

    def incomplete(obj) -> bool:
        links = obj.download_links or []
        return not (download_links_imply_dub(links) and download_links_imply_subtitle(links))

    connector = get_connector(_link_provider_slug())
    connector.authenticate()

    movies = list(Movie.objects.filter(is_published=True, created_at__gte=since).order_by('-id')) if do_movies else []
    series = list(Series.objects.filter(is_published=True, created_at__gte=since).order_by('-id')) if do_series else []
    print(f'recent movies={len(movies)} series={len(series)} since={since.isoformat()}', flush=True)

    stats = {
        'movie_crawl': 0,
        'movie_ok': 0,
        'movie_both': 0,
        'series_crawl': 0,
        'series_both': 0,
        'soft_m': 0,
        'soft_s': 0,
    }

    for movie in movies:
        if incomplete(movie):
            stats['movie_crawl'] += 1
            print(f'[movie crawl] id={movie.pk} {movie.title}', flush=True)
            try:
                result = _crawl_movie_links(movie, connector, replace=True)
                movie.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'subtitle_tracks'])
                apply_availability_flags(movie, movie.download_links or [])
                movie.save(update_fields=['is_dubbed', 'has_subtitle', 'updated_at'])
                if result.get('status') == 'ok':
                    stats['movie_ok'] += 1
                dub = download_links_imply_dub(movie.download_links or [])
                sub = download_links_imply_subtitle(movie.download_links or [])
                if dub and sub:
                    stats['movie_both'] += 1
                    print(f'  -> both ready links={len(movie.download_links or [])}', flush=True)
                else:
                    print(
                        f'  -> {result.get("status")} dub={dub} sub={sub} '
                        f'links={len(movie.download_links or [])}',
                        flush=True,
                    )
            except Exception as exc:
                print(f'  -> ERR {type(exc).__name__}: {exc}', flush=True)
            if delay:
                time.sleep(delay)

        movie.refresh_from_db(fields=['download_links', 'subtitle_tracks'])
        # SoftSub enqueue is optional — Celery/ensure pipelines own VTT backfill so
        # enrich can focus on dub/sub download links without flooding the queue.
        if not os.environ.get('ENRICH_SKIP_SOFTSUB_ENQUEUE'):
            if (movie.download_links or []) and not movie.subtitle_tracks:
                if enqueue_movie_softsub(movie.pk, force=True):
                    stats['soft_m'] += 1

    for series_row in series:
        if incomplete(series_row) or not (series_row.download_links or []):
            stats['series_crawl'] += 1
            print(f'[series crawl] id={series_row.pk} {series_row.title}', flush=True)
            try:
                result = _crawl_series_links(series_row, connector, replace=True)
                series_row.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle'])
                apply_availability_flags(series_row, series_row.download_links or [])
                series_row.save(update_fields=['is_dubbed', 'has_subtitle', 'updated_at'])
                dub = download_links_imply_dub(series_row.download_links or [])
                sub = download_links_imply_subtitle(series_row.download_links or [])
                if (series_row.download_links or []) and dub and sub:
                    stats['series_both'] += 1
                print(
                    f'  -> {result.get("status")} dub={dub} sub={sub} '
                    f'links={len(series_row.download_links or [])}',
                    flush=True,
                )
            except Exception as exc:
                print(f'  -> ERR {type(exc).__name__}: {exc}', flush=True)
            if delay:
                time.sleep(delay)

        if not os.environ.get('ENRICH_SKIP_SOFTSUB_ENQUEUE'):
            if enqueue_series_softsub(series_row.pk, force=True, episode_limit=100):
                stats['soft_s'] += 1

    print('STATS', stats, flush=True)

    if movies:
        both = vtt = 0
        for movie in Movie.objects.filter(is_published=True, created_at__gte=since).only(
            'download_links', 'subtitle_tracks',
        ):
            links = movie.download_links or []
            if download_links_imply_dub(links) and download_links_imply_subtitle(links):
                both += 1
            if movie.subtitle_tracks:
                vtt += 1
        print(f'coverage movies both={both}/{len(movies)} with_vtt={vtt}', flush=True)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
