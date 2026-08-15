#!/usr/bin/env python
"""Place IMDb Top 250 TV series on the site without rewriting existing catalog rows.

- Missing titles: TMDB import + Film2Media crawl + publish.
- Existing titles with no download box: crawl links only (no metadata upsert).
- Existing titles that already have links: left untouched.
- SoftSub WebVTT is queued so online playback can show synced Persian cues.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.db import transaction

from apps.catalog.imdb_charts import imdb_top_series
from apps.catalog.ingestion import upsert_tmdb_series
from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
from apps.catalog.models import Episode, Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub
from apps.catalog.top_catalog import (
    _crawl_series_links,
    _has_download_links,
    _suppress_provider_publish_signals,
    _version_coverage,
)
from apps.catalog.tmdb import configured_tmdb_client

LIMIT = int(os.environ.get('IMDB_TOP_SERIES_LIMIT', '250'))
CRAWL_DELAY = float(os.environ.get('IMDB_TOP_CRAWL_DELAY', '0.35'))


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


def _publish(series: Series) -> bool:
    if series.is_published:
        return False
    series.is_published = True
    series.save(update_fields=['is_published', 'updated_at'])
    return True


def main() -> int:
    started = time.time()
    chart = imdb_top_series(limit=LIMIT)
    client = configured_tmdb_client()
    print(f'=== IMDb Top {len(chart)} series → site (preserve existing) ===', flush=True)

    from apps.catalog.provider_import.registry import get_connector

    connector = get_connector('myf2m')
    connector.authenticate()

    stats = {
        'chart': len(chart),
        'tmdb_miss': 0,
        'iranian_skip': 0,
        'existing_untouched': 0,
        'existing_crawl': 0,
        'created': 0,
        'published': 0,
        'crawl_ok': 0,
        'crawl_fail': 0,
        'both': 0,
        'softsub_queued': 0,
        'errors': [],
    }

    by_imdb = {
        s.imdb_id: s
        for s in Series.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='')
        if s.imdb_id
    }
    by_tmdb = {
        int(tid): s
        for tid, s in Series.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', 'id')
    }
    # Refresh objects by pk lazily when needed.
    series_by_pk = {s.pk: s for s in Series.objects.all().only(
        'id', 'tmdb_id', 'imdb_id', 'title', 'is_published', 'download_links',
        'has_subtitle', 'is_dubbed', 'original_language',
    )}

    touched_ids: set[int] = set()

    with _suppress_provider_publish_signals():
        for item in chart:
            label = f'#{item.rank} {item.primary_title} ({item.imdb_id})'
            try:
                hit = client.resolve_imdb_to_tmdb(item.imdb_id, content_type='series')
            except Exception as exc:
                stats['errors'].append({'imdb_id': item.imdb_id, 'error': f'tmdb_find:{exc}'[:300]})
                stats['tmdb_miss'] += 1
                continue
            if not hit:
                stats['tmdb_miss'] += 1
                stats['errors'].append({'imdb_id': item.imdb_id, 'title': item.primary_title, 'error': 'tmdb_find_miss'})
                print(f'[miss] {label}', flush=True)
                continue

            tmdb_id = int(hit['id'])
            series = by_imdb.get(item.imdb_id)
            if series is None:
                pk = by_tmdb.get(tmdb_id)
                series = series_by_pk.get(pk) if pk else None

            if series is not None:
                series.refresh_from_db()
                if is_iranian_catalog_item(series):
                    stats['iranian_skip'] += 1
                    continue
                if _has_download_links(series):
                    # Preserve existing catalog rows completely.
                    if not series.is_published:
                        if _publish(series):
                            stats['published'] += 1
                            print(f'[publish-existing] {label}', flush=True)
                    cov = _version_coverage(series)
                    if cov['has_both']:
                        stats['both'] += 1
                    stats['existing_untouched'] += 1
                    touched_ids.add(series.pk)
                    continue

                # Existing row but no download box yet — crawl only.
                print(f'[crawl-existing] {label}', flush=True)
                stats['existing_crawl'] += 1
                crawl_result = _crawl_series_links(series, connector, replace=False)
                series.refresh_from_db()
                if crawl_result.get('status') == 'ok' and _has_download_links(series):
                    stats['crawl_ok'] += 1
                    if _publish(series):
                        stats['published'] += 1
                    if _version_coverage(series)['has_both']:
                        stats['both'] += 1
                else:
                    stats['crawl_fail'] += 1
                    stats['errors'].append({
                        'imdb_id': item.imdb_id,
                        'tmdb_id': tmdb_id,
                        'title': item.primary_title,
                        'error': crawl_result.get('code') or crawl_result.get('status') or 'crawl_failed',
                    })
                touched_ids.add(series.pk)
                if CRAWL_DELAY > 0:
                    time.sleep(CRAWL_DELAY)
                continue

            # Brand-new title.
            try:
                details = client.tv_details(tmdb_id)
            except Exception as exc:
                stats['errors'].append({'tmdb_id': tmdb_id, 'error': f'tv_details:{exc}'[:300]})
                continue
            if is_iranian_tmdb_details(details):
                stats['iranian_skip'] += 1
                continue

            print(f'[create] {label}', flush=True)
            try:
                with transaction.atomic():
                    series, created = upsert_tmdb_series(details)
                if not created:
                    # Race / already inserted under another id path.
                    if _has_download_links(series):
                        stats['existing_untouched'] += 1
                        touched_ids.add(series.pk)
                        continue
                else:
                    stats['created'] += 1
                # Prefer chart IMDb id when TMDB payload lacked it.
                if not series.imdb_id:
                    series.imdb_id = item.imdb_id
                    series.save(update_fields=['imdb_id', 'updated_at'])
            except Exception as exc:
                stats['errors'].append({'tmdb_id': tmdb_id, 'error': str(exc)[:300]})
                continue

            crawl_result = _crawl_series_links(series, connector, replace=False)
            series.refresh_from_db()
            if crawl_result.get('status') == 'ok' and _has_download_links(series):
                stats['crawl_ok'] += 1
                if _publish(series):
                    stats['published'] += 1
                if _version_coverage(series)['has_both']:
                    stats['both'] += 1
            else:
                stats['crawl_fail'] += 1
                stats['errors'].append({
                    'imdb_id': item.imdb_id,
                    'tmdb_id': tmdb_id,
                    'title': item.primary_title,
                    'error': crawl_result.get('code') or crawl_result.get('status') or 'crawl_failed',
                })
            touched_ids.add(series.pk)
            by_imdb[item.imdb_id] = series
            by_tmdb[tmdb_id] = series.pk
            series_by_pk[series.pk] = series
            if CRAWL_DELAY > 0:
                time.sleep(CRAWL_DELAY)

    close = getattr(connector, 'close', None)
    if callable(close):
        close()

    # SoftSub → synced WebVTT for online player (additive; does not rewrite links).
    for series in Series.objects.filter(pk__in=touched_ids, is_published=True).iterator():
        if not download_links_imply_softsub(series.download_links or []):
            continue
        total, with_tracks = _episode_track_coverage(series)
        if total and with_tracks >= total:
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
            stats['softsub_queued'] += 1

    # Also queue SoftSub for already-complete published Top-250 rows that still lack VTT
    # (additive track extract only — download boxes stay untouched).
    chart_imdb = {c.imdb_id for c in chart}
    for series in Series.objects.filter(imdb_id__in=chart_imdb, is_published=True).iterator():
        if series.pk in touched_ids:
            continue
        if not download_links_imply_softsub(series.download_links or []):
            continue
        total, with_tracks = _episode_track_coverage(series)
        if total and with_tracks >= total:
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
            stats['softsub_queued'] += 1

    # Coverage snapshot for the chart set.
    final_ids = chart_imdb
    final_rows = list(Series.objects.filter(imdb_id__in=final_ids))
    pub = [s for s in final_rows if s.is_published]
    with_links = sum(1 for s in pub if _has_download_links(s))
    both = sum(1 for s in pub if _version_coverage(s)['has_both'])
    soft = sum(1 for s in pub if download_links_imply_softsub(s.download_links or []))
    print('STATS', {k: v for k, v in stats.items() if k != 'errors'}, flush=True)
    print(
        f'COVERAGE in_db={len(final_rows)} published={len(pub)} with_links={with_links} '
        f'both_dub_sub={both} soft={soft} softsub_queued={stats["softsub_queued"]} '
        f'elapsed_s={int(time.time() - started)}',
        flush=True,
    )
    if stats['errors']:
        print('ERRORS_SAMPLE', stats['errors'][:40], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
