#!/usr/bin/env python
"""Recrawl IMDb Top-250 series that still lack download boxes (after myf2m fixes)."""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.imdb_charts import imdb_top_series
from apps.catalog.ingestion import upsert_tmdb_series
from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
from apps.catalog.models import Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub
from apps.catalog.top_catalog import (
    _crawl_series_links,
    _has_download_links,
    _suppress_provider_publish_signals,
    _version_coverage,
)
from apps.catalog.tmdb import configured_tmdb_client
from django.db import transaction

LIMIT = int(os.environ.get('IMDB_TOP_SERIES_LIMIT', '250'))
CRAWL_DELAY = float(os.environ.get('IMDB_TOP_CRAWL_DELAY', '0.4'))


def main() -> int:
    chart = imdb_top_series(limit=LIMIT)
    client = configured_tmdb_client()
    from apps.catalog.provider_import.registry import get_connector

    connector = get_connector('myf2m')
    connector.authenticate()

    stats = {
        'need': 0, 'ok': 0, 'fail': 0, 'created': 0, 'published': 0,
        'both': 0, 'soft_q': 0, 'skip_has_links': 0, 'errors': [],
    }

    with _suppress_provider_publish_signals():
        for item in chart:
            label = f'#{item.rank} {item.primary_title}'
            series = Series.objects.filter(imdb_id=item.imdb_id).first()
            if series is None:
                hit = client.resolve_imdb_to_tmdb(item.imdb_id, content_type='series')
                if not hit:
                    stats['errors'].append({'imdb_id': item.imdb_id, 'error': 'tmdb_miss'})
                    continue
                details = client.tv_details(int(hit['id']))
                if is_iranian_tmdb_details(details):
                    continue
                with transaction.atomic():
                    series, created = upsert_tmdb_series(details)
                if created:
                    stats['created'] += 1
                if not series.imdb_id:
                    series.imdb_id = item.imdb_id
                    series.save(update_fields=['imdb_id', 'updated_at'])

            series.refresh_from_db()
            if is_iranian_catalog_item(series):
                continue
            if _has_download_links(series):
                stats['skip_has_links'] += 1
                if not series.is_published:
                    series.is_published = True
                    series.save(update_fields=['is_published', 'updated_at'])
                    stats['published'] += 1
                continue

            stats['need'] += 1
            print(f'[crawl] {label}', flush=True)
            result = _crawl_series_links(series, connector, replace=False)
            series.refresh_from_db()
            if result.get('status') == 'ok' and _has_download_links(series):
                stats['ok'] += 1
                if not series.is_published:
                    series.is_published = True
                    series.save(update_fields=['is_published', 'updated_at'])
                    stats['published'] += 1
                cov = _version_coverage(series)
                if cov['has_both']:
                    stats['both'] += 1
                if download_links_imply_softsub(series.download_links or []):
                    if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
                        stats['soft_q'] += 1
                print(f'  -> ok links={len(series.download_links or [])} both={cov["has_both"]}', flush=True)
            else:
                stats['fail'] += 1
                stats['errors'].append({
                    'imdb_id': item.imdb_id,
                    'title': item.primary_title,
                    'error': result.get('code') or result.get('status'),
                })
                print(f'  -> fail {result.get("code") or result.get("status")}', flush=True)
            if CRAWL_DELAY > 0:
                time.sleep(CRAWL_DELAY)

    close = getattr(connector, 'close', None)
    if callable(close):
        close()

    print('STATS', {k: v for k, v in stats.items() if k != 'errors'}, flush=True)
    if stats['errors']:
        print('ERRORS', stats['errors'][:40], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
