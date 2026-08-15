#!/usr/bin/env python3
"""Refresh myf2m links for Soft-only series (no HardSub) then queue SoftSub VTT.

Online SoftSub needs either:
  1) live Soft CDN + WebVTT (ffmpeg / SubtitleStar), or
  2) live HardSub as burned-in fallback until SoftSub cues arrive.

Many Soft-only rows still point at dead cdnhost.lol mirrors — re-crawl first.
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

    from django.core.cache import cache
    from django.db.models import Q

    from apps.catalog.models import Episode, Series
    from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_series
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.subtitle_extract import (
        download_links_imply_softsub,
        looks_like_hardsub_link,
        url_implies_softsub,
    )
    from apps.catalog.tasks import _softsub_queue_lock, extract_series_softsub_task

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--episode-limit', type=int, default=80)
    parser.add_argument('--pause-seconds', type=float, default=3.0)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-crawl', action='store_true')
    parser.add_argument('--include-dub-only', action='store_true')
    args = parser.parse_args()

    candidates: list[Series] = []
    for series in Series.objects.filter(is_published=True).order_by('-popularity', 'id').iterator(chunk_size=80):
        links = [item for item in (series.download_links or []) if isinstance(item, dict)]
        hard = any(looks_like_hardsub_link(item) for item in links)
        if hard:
            continue
        soft = any(url_implies_softsub(item) for item in links) or download_links_imply_softsub(links)
        if not soft and not args.include_dub_only:
            continue
        missing = Episode.objects.filter(
            season__series_id=series.pk,
            is_published=True,
        ).filter(Q(subtitle_tracks__isnull=True) | Q(subtitle_tracks=[])).exclude(
            video_url='',
        ).exclude(video_url__isnull=True).exists()
        # Soft-only with dead Soft still needs crawl even when some VTT exists.
        if soft or missing:
            candidates.append(series)

    if args.limit:
        candidates = candidates[: max(1, int(args.limit))]

    print(f'candidates={len(candidates)} dry_run={args.dry_run}', flush=True)
    stats = {'crawled': 0, 'crawl_fail': 0, 'queued': 0, 'skipped_lock': 0}

    for index, series in enumerate(candidates, start=1):
        print(f'[{index}/{len(candidates)}] id={series.pk} {series.title}', flush=True)
        if args.dry_run:
            continue
        if not args.skip_crawl:
            try:
                result = crawl_myf2m_downloads_for_series(
                    series=series,
                    replace=False,
                    queue_softsub_extract=False,
                )
                stats['crawled'] += 1
                print(
                    f'  crawl ok imported={result.get("imported_count")} path={result.get("page_path")}',
                    flush=True,
                )
            except ProviderImportError as exc:
                stats['crawl_fail'] += 1
                print(f'  crawl skip: {exc}', flush=True)
            except Exception as exc:
                stats['crawl_fail'] += 1
                print(f'  crawl error: {type(exc).__name__}: {exc}', flush=True)

        lock = _softsub_queue_lock('series', series.pk)
        cache.delete(lock)
        if not cache.add(lock, 'queued', timeout=2 * 60 * 60):
            stats['skipped_lock'] += 1
            continue
        try:
            extract_series_softsub_task.apply_async(
                args=[series.pk],
                kwargs={'force': False, 'episode_limit': max(1, int(args.episode_limit))},
                countdown=int((index - 1) * 15),
            )
        except Exception:
            cache.delete(lock)
            raise
        stats['queued'] += 1
        time.sleep(max(0.0, float(args.pause_seconds)))

    print('REFRESH_SERIES_SOFT_NO_HARD_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
