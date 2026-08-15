#!/usr/bin/env python
"""Keep SoftSub episode tracks filling for published series with soft links."""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.models import Episode, Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub


def _coverage(series: Series) -> tuple[int, int]:
    eps = list(
        Episode.objects.filter(season__series=series, is_published=True).only(
            'id', 'subtitle_tracks', 'video_url'
        )
    )
    with_tracks = 0
    with_video = 0
    for ep in eps:
        if any(
            isinstance(t, dict) and str(t.get('src') or t.get('key') or '').strip()
            for t in (ep.subtitle_tracks or [])
        ):
            with_tracks += 1
        if str(ep.video_url or '').strip():
            with_video += 1
    return len(eps), with_tracks, with_video


def main() -> int:
    rounds = int(os.environ.get('SOFTSUB_DRAIN_ROUNDS', '40'))
    sleep_s = float(os.environ.get('SOFTSUB_DRAIN_SLEEP', '90'))
    for round_no in range(1, rounds + 1):
        need = []
        complete = 0
        no_soft = 0
        for series in Series.objects.filter(is_published=True).iterator():
            if not download_links_imply_softsub(series.download_links or []):
                no_soft += 1
                continue
            total, tracks, videos = _coverage(series)
            if total <= 0:
                continue
            if tracks >= total:
                complete += 1
                continue
            need.append((series.pk, series.original_title or series.title, total, tracks, videos))

        queued = 0
        for pk, title, total, tracks, videos in need:
            if enqueue_series_softsub(pk, force=False, episode_limit=60):
                queued += 1
                print(
                    f'[round {round_no}] queue {pk} {title} tracks={tracks}/{total} video={videos}/{total}',
                    flush=True,
                )
        print(
            f'[round {round_no}] need={len(need)} queued={queued} complete={complete} no_soft={no_soft}',
            flush=True,
        )
        if not need:
            print('DONE all soft series have episode tracks', flush=True)
            return 0
        time.sleep(sleep_s)
    print('STOP hit max rounds; remaining softseries still incomplete', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
