#!/usr/bin/env python3
"""Refresh published series download boxes so newly released episodes appear."""

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


def _page_path(series) -> str:
    for item in series.download_links or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get('page_path') or '').strip()
        if path.startswith('/series/'):
            return path
    return ''


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.models import Episode, Series
    from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_series
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.top_catalog import _suppress_provider_publish_signals

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.7)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--popularity-min', type=float, default=0.0)
    parser.add_argument(
        '--year-min',
        type=int,
        default=0,
        help='Only series whose start_year or end_year is >= this (e.g. 2025 for current airing)',
    )
    args = parser.parse_args()
    workers = max(1, min(8, int(args.workers)))
    request_interval = max(0.0, float(args.delay))

    qs = (
        Series.objects.filter(is_published=True)
        .exclude(download_links=[])
        .exclude(download_links__isnull=True)
        .order_by('-popularity', '-updated_at', '-id')
    )
    series_rows = [s for s in qs.iterator(chunk_size=100) if _page_path(s)]
    if args.year_min:
        year_min = int(args.year_min)
        series_rows = [
            s for s in series_rows
            if (int(s.start_year or 0) >= year_min) or (int(s.end_year or 0) >= year_min)
        ]
    if args.popularity_min:
        series_rows = [s for s in series_rows if float(s.popularity or 0) >= args.popularity_min]
    if args.limit:
        series_rows = series_rows[: max(1, args.limit)]

    before_eps = Episode.objects.filter(is_published=True).count()
    stats = {
        'tried': 0,
        'ok': 0,
        'failed': 0,
        'episodes_before': before_eps,
        'created_total': 0,
    }
    print(f'refresh_series={len(series_rows)} episodes_before={before_eps} workers={workers}', flush=True)

    pace_lock = threading.Lock()
    next_request_at = [0.0]

    def refresh_one(series_id: int, page: str):
        from django.db import close_old_connections

        close_old_connections()
        with pace_lock:
            wait = next_request_at[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            next_request_at[0] = time.monotonic() + request_interval
        try:
            series = Series.objects.get(pk=series_id)
            eps_before = Episode.objects.filter(season__series_id=series_id).count()
            result = crawl_myf2m_downloads_for_series(
                series=series,
                page_url=page,
                replace=True,
                queue_softsub_extract=True,
            )
            series.refresh_from_db(fields=['download_links', 'updated_at', 'has_subtitle', 'is_dubbed'])
            eps_after = Episode.objects.filter(season__series_id=series_id).count()
            return 'ok', result.get('imported_count') or len(series.download_links or []), max(0, eps_after - eps_before)
        except ProviderImportError as exc:
            return 'fail', getattr(exc, 'code', ''), str(exc)
        except Exception as exc:
            return 'error', type(exc).__name__, str(exc)
        finally:
            close_old_connections()

    with _suppress_provider_publish_signals():
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='series-refresh') as pool:
            pending = {
                pool.submit(refresh_one, series.pk, _page_path(series)): series
                for series in series_rows
            }
            for future in as_completed(pending):
                series = pending[future]
                stats['tried'] += 1
                status, first, second = future.result()
                if status == 'ok':
                    created = int(second)
                    links = int(first)
                    stats['ok'] += 1
                    stats['created_total'] += created
                    print(
                        f'[{stats["tried"]}/{len(series_rows)}] ok series={series.pk} {series.title} '
                        f'links={links} new_episodes={created}',
                        flush=True,
                    )
                else:
                    stats['failed'] += 1
                    print(
                        f'[{stats["tried"]}/{len(series_rows)}] {status} series={series.pk} '
                        f'{series.title} {first} {second}',
                        flush=True,
                    )

    after_eps = Episode.objects.filter(is_published=True).count()
    stats['episodes_after'] = after_eps
    stats['episodes_delta'] = after_eps - before_eps
    print('REFRESH_SERIES_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
