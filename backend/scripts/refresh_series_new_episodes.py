#!/usr/bin/env python3
"""Refresh published series download boxes so newly released episodes appear."""

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
    parser.add_argument('--popularity-min', type=float, default=0.0)
    parser.add_argument(
        '--year-min',
        type=int,
        default=0,
        help='Only series whose start_year or end_year is >= this (e.g. 2025 for current airing)',
    )
    args = parser.parse_args()

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
    print(f'refresh_series={len(series_rows)} episodes_before={before_eps}', flush=True)

    with _suppress_provider_publish_signals():
        for series in series_rows:
            stats['tried'] += 1
            page = _page_path(series)
            eps_before = Episode.objects.filter(season__series_id=series.pk).count()
            print(
                f'[{stats["tried"]}/{len(series_rows)}] series={series.pk} {series.title} page={page}',
                flush=True,
            )
            try:
                result = crawl_myf2m_downloads_for_series(
                    series=series,
                    page_url=page,
                    replace=True,
                    queue_softsub_extract=True,
                )
                series.refresh_from_db(fields=['download_links', 'updated_at', 'has_subtitle', 'is_dubbed'])
                eps_after = Episode.objects.filter(season__series_id=series.pk).count()
                created = max(0, eps_after - eps_before)
                stats['ok'] += 1
                stats['created_total'] += created
                print(
                    f'  -> ok links={result.get("imported_count") or len(series.download_links or [])} '
                    f'new_episodes={created}',
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

    after_eps = Episode.objects.filter(is_published=True).count()
    stats['episodes_after'] = after_eps
    stats['episodes_delta'] = after_eps - before_eps
    print('REFRESH_SERIES_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
