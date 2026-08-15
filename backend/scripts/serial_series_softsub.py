#!/usr/bin/env python3
"""Serially attach SubtitleStar tracks for published series missing episode VTT."""

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

    from django.conf import settings
    from django.core.cache import cache
    from django.db import connection

    from apps.catalog.models import Series
    from apps.catalog.subtitle_extract import attach_series_softsub_tracks

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-limit', type=int, default=200)
    parser.add_argument('--pause-seconds', type=float, default=15.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--wait-circuit', action='store_true', default=True)
    parser.add_argument('--no-wait-circuit', action='store_false', dest='wait_circuit')
    args = parser.parse_args()

    if args.wait_circuit:
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('waiting for SubtitleStar circuit...', flush=True)
            time.sleep(30)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.id
            FROM catalog_series s
            WHERE s.is_published
              AND EXISTS (
                SELECT 1
                FROM catalog_season se
                JOIN catalog_episode e ON e.season_id = se.id
                WHERE se.series_id = s.id
                  AND e.is_published
                  AND COALESCE(e.video_url, '') <> ''
                  AND (e.subtitle_tracks IS NULL OR e.subtitle_tracks::text IN ('[]', 'null'))
              )
            ORDER BY s.popularity DESC NULLS LAST, s.id
            """
        )
        series_ids = [int(row[0]) for row in cursor.fetchall()]
    if args.limit:
        series_ids = series_ids[: max(1, args.limit)]

    stats = {'tried': 0, 'attached': 0, 'empty': 0, 'blocked': 0}
    print(
        f'serial_softsub series={len(series_ids)} '
        f'interval={getattr(settings, "SUBTITLESTAR_REQUEST_INTERVAL_SECONDS", None)}',
        flush=True,
    )

    for index, series_id in enumerate(series_ids, start=1):
        if cache.get('catalog:subtitlestar:circuit-open'):
            stats['blocked'] += 1
            print(f'[{index}/{len(series_ids)}] circuit open — pausing 60s', flush=True)
            time.sleep(60)
            if cache.get('catalog:subtitlestar:circuit-open'):
                print('circuit still open — stop; rerun later', flush=True)
                break

        series = Series.objects.filter(pk=series_id, is_published=True).first()
        if series is None:
            continue
        stats['tried'] += 1
        print(f'[{index}/{len(series_ids)}] series={series_id} {series.title}', flush=True)
        result = attach_series_softsub_tracks(
            series,
            timeout_seconds=120,
            limit=max(1, int(args.episode_limit)),
        )
        attached = int(result.get('extracted') or 0)
        stats['attached'] += attached
        if attached:
            print(f'  -> attached={attached} matches={result.get("subtitlestar_matches")}', flush=True)
        else:
            stats['empty'] += 1
            print('  -> no matches', flush=True)

        if cache.get('catalog:subtitlestar:circuit-open'):
            stats['blocked'] += 1
            print('circuit opened — stop; rerun later', flush=True)
            break
        time.sleep(max(0.0, float(args.pause_seconds)))

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FILTER (
              WHERE subtitle_tracks IS NOT NULL AND subtitle_tracks::text NOT IN ('[]', 'null')
            )
            FROM catalog_episode
            WHERE is_published
            """
        )
        stats['with_tracks'] = cursor.fetchone()[0]
    print('SERIAL_SOFTSUB_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
