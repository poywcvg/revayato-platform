#!/usr/bin/env python3
"""Queue SoftSub WebVTT for published series that have no HardSub encode.

Online player rule: SoftSub+cues → HardSub burned-in → Dub. Titles without
HardSub must get episode WebVTT (SubtitleStar or Soft ffmpeg demux) so Persian
text is visible and cue-timed to the Soft encode.
"""

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

    from apps.catalog.models import Episode, Series
    from apps.catalog.subtitle_extract import (
        download_links_imply_softsub,
        looks_like_hardsub_link,
        url_implies_softsub,
    )
    from apps.catalog.tasks import _softsub_queue_lock, extract_series_softsub_task

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-limit', type=int, default=80)
    parser.add_argument('--stagger-seconds', type=float, default=20.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--force', action='store_true')
    parser.add_argument(
        '--include-dub-only',
        action='store_true',
        help='Also queue dub-only titles (need SubtitleStar; skipped while circuit is open).',
    )
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    candidates: list[tuple[int, str, int, bool]] = []
    for series in Series.objects.filter(is_published=True).order_by('-popularity', 'id').iterator(chunk_size=80):
        links = [item for item in (series.download_links or []) if isinstance(item, dict)]
        if any(looks_like_hardsub_link(item) for item in links):
            continue
        has_soft = any(url_implies_softsub(item) for item in links) or download_links_imply_softsub(links)
        if not has_soft and not args.include_dub_only:
            continue
        missing = Episode.objects.filter(
            season__series_id=series.pk,
            is_published=True,
        ).filter(
            models_q_missing(),
        ).exclude(video_url='').exclude(video_url__isnull=True).count()
        if missing <= 0:
            continue
        candidates.append((series.pk, series.title or '', missing, has_soft))

    if args.limit:
        candidates = candidates[: max(1, int(args.limit))]

    print(
        f'no-hard gaps={len(candidates)} soft_only={sum(1 for *_, soft in candidates if soft)} '
        f'episode_limit={args.episode_limit}',
        flush=True,
    )
    if args.dry_run:
        for series_id, title, missing, has_soft in candidates:
            print(f'  id={series_id} missing={missing} soft={has_soft} {title}', flush=True)
        return 0

    queued = 0
    skipped = 0
    for index, (series_id, title, missing, has_soft) in enumerate(candidates):
        lock = _softsub_queue_lock('series', series_id)
        cache.delete(lock)
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
        print(
            f'queued series={series_id} missing={missing} soft={has_soft} '
            f'countdown={countdown}s {title}',
            flush=True,
        )

    print(f'DONE queued={queued} skipped={skipped}', flush=True)
    return 0


def models_q_missing():
    from django.db.models import Q
    return Q(subtitle_tracks__isnull=True) | Q(subtitle_tracks=[])


if __name__ == '__main__':
    raise SystemExit(main())
