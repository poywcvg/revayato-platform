#!/usr/bin/env python
"""Fill catalog toward 250 published series with myf2m download boxes."""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.models import Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub
from apps.catalog.top_catalog import (
    _has_download_links,
    _version_coverage,
    import_top_catalog,
)


TARGET = int(os.environ.get('SERIES_WITH_LINKS_TARGET', '250'))


def _published_with_links() -> int:
    return sum(
        1
        for s in Series.objects.filter(is_published=True).iterator()
        if _has_download_links(s)
    )


def _coverage_snapshot(label: str) -> None:
    pub = list(Series.objects.filter(is_published=True))
    links = dub = sub = both = soft = 0
    for s in pub:
        if _has_download_links(s):
            links += 1
        cov = _version_coverage(s)
        dub += int(cov['has_dub'])
        sub += int(cov['has_sub'])
        both += int(cov['has_both'])
        soft += int(download_links_imply_softsub(s.download_links or []))
    print(
        f'[{label}] published={len(pub)} with_links={links} dub={dub} sub={sub} both={both} soft={soft}',
        flush=True,
    )


def _unpublish_without_links() -> int:
    n = 0
    for series in Series.objects.filter(is_published=True).iterator():
        if _has_download_links(series):
            continue
        series.is_published = False
        series.save(update_fields=['is_published', 'updated_at'])
        n += 1
    return n


def main() -> int:
    started = time.time()
    _coverage_snapshot('before')
    current = _published_with_links()
    print(f'target={TARGET} current_with_links={current}', flush=True)

    def on_progress(phase, label, stats):
        if phase in {'series_import', 'series_crawl', 'series_removed_no_links'}:
            print(
                f'[{phase}] {label} | discovered={stats.get("series_discovered")} '
                f'created={stats.get("series_created")} links_ok={stats.get("series_crawled_ok")} '
                f'both={stats.get("series_with_both")}',
                flush=True,
            )

    # Popular list usually maps better onto Persian providers than pure top_rated.
    if current < TARGET:
        print('=== import popular series limit=350 ===', flush=True)
        stats = import_top_catalog(
            limit=350,
            import_movies=False,
            import_series=True,
            publish=True,
            crawl=True,
            replace_links=False,
            skip_existing_links=True,
            skip_existing_titles=False,
            require_provider_links=False,
            crawl_delay_seconds=0.25,
            source='popular',
            on_progress=on_progress,
        )
        print('POPULAR_STATS', {k: stats[k] for k in stats if k != 'errors'}, flush=True)
        if stats.get('errors'):
            print('POPULAR_ERRORS', stats['errors'][:20], flush=True)

    unpublished = _unpublish_without_links()
    print(f'unpublished_without_links={unpublished}', flush=True)
    _coverage_snapshot('after_popular')

    # Second pass: re-crawl published titles still missing dub+sub coverage.
    print('=== crawl_only pass for missing dub/sub ===', flush=True)
    crawl_stats = import_top_catalog(
        limit=400,
        import_movies=False,
        import_series=True,
        publish=True,
        crawl=True,
        crawl_only=True,
        replace_links=False,
        skip_existing_links=True,
        require_provider_links=False,
        crawl_delay_seconds=0.25,
        source='popular',
        on_progress=on_progress,
    )
    print('CRAWL_ONLY_STATS', {k: crawl_stats[k] for k in crawl_stats if k != 'errors'}, flush=True)
    unpublished = _unpublish_without_links()
    print(f'unpublished_without_links={unpublished}', flush=True)
    _coverage_snapshot('final')

    # SoftSub queue top-up (locks may already hold most).
    queued = 0
    for series in Series.objects.filter(is_published=True).iterator():
        if not download_links_imply_softsub(series.download_links or []):
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
            queued += 1
    print(f'softsub_queued={queued} elapsed_s={int(time.time() - started)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
