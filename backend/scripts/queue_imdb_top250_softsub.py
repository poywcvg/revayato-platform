#!/usr/bin/env python
"""Queue SoftSub WebVTT extraction for published IMDb Top-250 series.

Additive only — does not rewrite download_links. Extracted tracks power synced
online playback (pairSubtitleTracksForSource / VideoPlayer).
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.imdb_charts import imdb_top_series
from apps.catalog.models import Episode, Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub

LIMIT = int(os.environ.get('IMDB_TOP_SERIES_LIMIT', '250'))
EPISODE_LIMIT = int(os.environ.get('SOFTSUB_EPISODE_LIMIT', '60'))


def _coverage(series: Series) -> tuple[int, int]:
    eps = list(
        Episode.objects.filter(season__series=series, is_published=True).only('subtitle_tracks')
    )
    with_tracks = sum(
        1
        for ep in eps
        if any(
            isinstance(t, dict) and str(t.get('src') or t.get('key') or '').strip()
            for t in (ep.subtitle_tracks or [])
        )
    )
    return len(eps), with_tracks


def main() -> int:
    chart = imdb_top_series(limit=LIMIT)
    ids = [c.imdb_id for c in chart]
    queued = skipped_no_soft = skipped_complete = skipped_lock = 0
    for series in Series.objects.filter(imdb_id__in=ids, is_published=True).iterator():
        if not download_links_imply_softsub(series.download_links or []):
            skipped_no_soft += 1
            continue
        total, tracks = _coverage(series)
        if total and tracks >= total:
            skipped_complete += 1
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=EPISODE_LIMIT):
            queued += 1
            print(f'[queue] {series.imdb_id} {series.title} eps={tracks}/{total}', flush=True)
        else:
            skipped_lock += 1
    print(
        f'DONE queued={queued} complete={skipped_complete} no_soft={skipped_no_soft} '
        f'locked={skipped_lock}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
