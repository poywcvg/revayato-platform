#!/usr/bin/env python
"""Import TMDB top-rated 250 series with myf2m download boxes + softsub queue."""

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
from apps.catalog.top_catalog import (
    _has_download_links,
    _version_coverage,
    import_top_catalog,
)


def _episode_track_coverage(series: Series) -> tuple[int, int]:
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
    started = time.time()
    print('=== import top_rated series limit=250 ===', flush=True)

    def on_progress(phase, label, stats):
        print(
            f'[{phase}] {label} | discovered={stats.get("series_discovered")} '
            f'created={stats.get("series_created")} updated={stats.get("series_updated")} '
            f'links_ok={stats.get("series_crawled_ok")} failed={stats.get("series_crawl_failed")} '
            f'both={stats.get("series_with_both")}',
            flush=True,
        )

    stats = import_top_catalog(
        limit=250,
        import_movies=False,
        import_series=True,
        publish=True,
        crawl=True,
        crawl_only=False,
        replace_links=False,
        skip_existing_links=True,
        skip_existing_titles=False,
        # Keep existing catalog rows even if a crawl miss happens mid-run.
        require_provider_links=False,
        crawl_delay_seconds=0.35,
        source='top_rated',
        on_progress=on_progress,
    )
    print('IMPORT_STATS', stats, flush=True)

    # Unpublish titles that still have no download box (useless for playback).
    unpublished = 0
    for series in Series.objects.filter(is_published=True).iterator():
        if _has_download_links(series):
            continue
        series.is_published = False
        series.save(update_fields=['is_published', 'updated_at'])
        unpublished += 1
    print(f'unpublished_without_links={unpublished}', flush=True)

    # Queue SoftSub extraction for published series that expose soft encodes.
    queued = 0
    skipped = 0
    for series in Series.objects.filter(is_published=True).iterator():
        links = series.download_links or []
        if not download_links_imply_softsub(links):
            skipped += 1
            continue
        ep_total, ep_tracks = _episode_track_coverage(series)
        # Re-queue while episodes still miss tracks (worker processes 24/run).
        if ep_total and ep_tracks >= ep_total:
            skipped += 1
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
            queued += 1
        else:
            skipped += 1
    print(f'softsub_queued={queued} softsub_skipped={skipped}', flush=True)

    # Final coverage snapshot for top-rated set.
    from apps.catalog.tmdb import configured_tmdb_client

    client = configured_tmdb_client()
    top_ids = [int(row['id']) for row in client.top_rated_tv(limit=250)]
    rows = list(Series.objects.filter(tmdb_id__in=top_ids))
    published = [s for s in rows if s.is_published]
    with_links = sum(1 for s in published if _has_download_links(s))
    dub = sub = both = soft = 0
    for s in published:
        cov = _version_coverage(s)
        dub += int(cov['has_dub'])
        sub += int(cov['has_sub'])
        both += int(cov['has_both'])
        soft += int(download_links_imply_softsub(s.download_links or []))
    print(
        f'COVERAGE top250_in_db={len(rows)} published={len(published)} '
        f'with_links={with_links} dub={dub} sub={sub} both={both} soft={soft} '
        f'elapsed_s={int(time.time() - started)}',
        flush=True,
    )
    if stats.get('errors'):
        print('ERRORS_SAMPLE', stats['errors'][:30], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
