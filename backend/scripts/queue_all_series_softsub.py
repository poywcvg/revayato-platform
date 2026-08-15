#!/usr/bin/env python3
"""Queue SoftSub / SubtitleStar extraction for every published series with gaps."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.core.cache import cache
    from django.db import connection

    from apps.catalog.models import Series
    from apps.catalog.tasks import extract_series_softsub_task, _softsub_queue_lock

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-limit', type=int, default=200)
    parser.add_argument('--stagger-seconds', type=float, default=25.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    cache.delete('catalog:subtitlestar:circuit-open')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT s.id
            FROM catalog_series s
            JOIN catalog_season se ON se.series_id = s.id
            JOIN catalog_episode e ON e.season_id = se.id
            WHERE s.is_published
              AND e.is_published
              AND COALESCE(e.video_url, '') <> ''
              AND (e.subtitle_tracks IS NULL OR e.subtitle_tracks::text IN ('[]', 'null'))
            ORDER BY s.id
            """
        )
        series_ids = [int(row[0]) for row in cursor.fetchall()]

    if args.limit:
        series_ids = series_ids[: max(1, args.limit)]

    queued = 0
    skipped = 0
    for index, series_id in enumerate(series_ids):
        lock = _softsub_queue_lock('series', series_id)
        if not cache.add(lock, 'queued', timeout=2 * 60 * 60):
            skipped += 1
            continue
        countdown = int(index * max(0.0, float(args.stagger_seconds)))
        try:
            extract_series_softsub_task.apply_async(
                args=[series_id],
                kwargs={
                    'force': bool(args.force),
                    'episode_limit': max(1, int(args.episode_limit)),
                },
                countdown=countdown,
            )
        except Exception:
            cache.delete(lock)
            raise
        queued += 1
        title = Series.objects.filter(pk=series_id).values_list('title', flat=True).first() or ''
        print(f'queued series={series_id} countdown={countdown}s {title}', flush=True)

    print(f'DONE queued={queued} skipped={skipped} total_candidates={len(series_ids)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
