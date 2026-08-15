"""Reconcile catalog download/playback links against Film2Media (myf2m.info).

Policy (Hollywood-only mirror of the public myf2m catalog):
1. Delete Iranian movies/series from our catalog.
2. For remaining published titles, crawl myf2m download boxes → download_links,
   online video_url / episode streams, and SoftSub WebVTT extraction.
3. If myf2m has no confident match / empty links → delete the catalog row.
4. Optional: import this week's TMDB releases and keep only titles with myf2m links.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Callable

from django.conf import settings
from django.db import transaction

from apps.catalog.iranian import (
    iranian_movie_queryset,
    iranian_series_queryset,
    is_iranian_catalog_item,
    is_iranian_tmdb_details,
)
from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
from apps.catalog.tmdb import configured_tmdb_client
from apps.catalog.top_catalog import (
    _crawl_movie_links,
    _crawl_series_links,
    _has_download_links,
    _suppress_provider_publish_signals,
    _version_coverage,
)

logger = logging.getLogger(__name__)


def _empty_stats() -> dict:
    return {
        'provider': 'myf2m',
        'iranian_movies_deleted': 0,
        'iranian_series_deleted': 0,
        'movies_scanned': 0,
        'movies_crawled_ok': 0,
        'movies_deleted': 0,
        'movies_skipped_complete': 0,
        'movies_rate_limited': 0,
        'movies_errors': 0,
        'movies_with_dub': 0,
        'movies_with_sub': 0,
        'movies_with_both': 0,
        'series_scanned': 0,
        'series_crawled_ok': 0,
        'series_deleted': 0,
        'series_skipped_complete': 0,
        'series_rate_limited': 0,
        'series_errors': 0,
        'series_with_dub': 0,
        'series_with_sub': 0,
        'series_with_both': 0,
        'errors': [],
    }


def purge_iranian_catalog(*, dry_run: bool = False) -> dict:
    """Remove Iranian cinema/TV from the local catalog."""
    movies = iranian_movie_queryset().distinct()
    series = iranian_series_queryset().distinct()
    movie_count = movies.count()
    series_count = series.count()
    if not dry_run:
        # Prefetch ids — delete() on distinct M2M joins can be ambiguous.
        movie_ids = list(movies.values_list('id', flat=True))
        series_ids = list(series.values_list('id', flat=True))
        if movie_ids:
            Movie.objects.filter(id__in=movie_ids).delete()
        if series_ids:
            Series.objects.filter(id__in=series_ids).delete()
    return {
        'iranian_movies_deleted': movie_count,
        'iranian_series_deleted': series_count,
    }


def reconcile_catalog_with_myf2m(
    *,
    delete_missing: bool = True,
    purge_iranian: bool = True,
    crawl_delay_seconds: float = 0.75,
    limit: int | None = None,
    movies: bool = True,
    series: bool = True,
    only_missing_links: bool = False,
    refresh_incomplete: bool = True,
    dry_run: bool = False,
    on_progress: Callable | None = None,
) -> dict:
    """Fill myf2m links for Hollywood titles; delete titles myf2m does not carry."""
    from apps.catalog.provider_import.registry import get_connector

    stats = _empty_stats()
    provider = (getattr(settings, 'CATALOG_LINK_PROVIDER', 'myf2m') or 'myf2m').strip().lower()
    if provider != 'myf2m':
        logger.warning(
            'CATALOG_LINK_PROVIDER=%s but reconcile is forcing myf2m crawler.',
            provider,
        )

    def notify(phase: str, label: str):
        if callable(on_progress):
            on_progress(phase, label, stats)

    if purge_iranian:
        notify('purge_iranian', 'removing Iranian catalog titles')
        purged = purge_iranian_catalog(dry_run=dry_run)
        stats['iranian_movies_deleted'] = purged['iranian_movies_deleted']
        stats['iranian_series_deleted'] = purged['iranian_series_deleted']

    connector = get_connector('myf2m')
    last_exc = None
    for attempt in range(1, 4):
        try:
            connector.authenticate()
            last_exc = None
            break
        except ProviderRateLimited as exc:
            last_exc = exc
            sleep_seconds = 20 * attempt
            logger.warning('myf2m auth rate-limited attempt %s/3; sleeping %ss', attempt, sleep_seconds)
            time.sleep(sleep_seconds)
        except ProviderImportError as exc:
            last_exc = exc
            sleep_seconds = 15 * attempt
            logger.warning('myf2m auth failed attempt %s/3: %s; sleeping %ss', attempt, exc, sleep_seconds)
            time.sleep(sleep_seconds)
    if last_exc is not None:
        raise last_exc

    def should_crawl(obj) -> bool:
        if is_iranian_catalog_item(obj):
            return False
        if not only_missing_links:
            # Full reconcile: re-check every Hollywood title against myf2m.
            return True
        if not _has_download_links(obj):
            return True
        if refresh_incomplete and not _version_coverage(obj)['has_both']:
            return True
        return False

    def crawl_priority(obj) -> tuple:
        # Enrich playable titles with dub+sub first, then fill/delete missing links.
        cov = _version_coverage(obj)
        return (
            0 if (cov['has_links'] and not cov['has_both']) else 1,
            0 if not cov['has_links'] else 1,
            -(float(getattr(obj, 'popularity', 0) or 0)),
            -(int(getattr(obj, 'id', 0) or 0)),
        )

    def maybe_delete(*, obj, label: str, had_links: bool, result: dict, content_type: str) -> bool:
        """Delete only when the title had no usable links and myf2m has no page.

        Titles that already stream/download keep their links if a dual-version
        refresh misses — avoids false-negative search wiping working catalog rows.
        """
        if not delete_missing:
            return False
        status = result.get('status')
        code = result.get('code') or ''
        missing_codes = {
            'myf2m_page_required', 'myf2m_links_empty',
            'myf2m_page_required', 'myf2m_links_empty',
        }
        is_miss = status == 'page_not_found' or code in missing_codes or (
            status == 'ok' and not _has_download_links(obj)
        )
        if not is_miss:
            return False
        if had_links and only_missing_links:
            # Dual-refresh miss: keep existing playback.
            return False
        if had_links and not only_missing_links:
            # Full reconcile still removes titles myf2m does not carry.
            pass
        elif had_links:
            return False
        notify(f'{content_type}_delete', label)
        obj.delete()
        return True

    try:
        with _suppress_provider_publish_signals():
            if movies:
                candidates = [
                    m for m in (
                        Movie.objects.filter(is_published=True)
                        .exclude(original_language__iexact='fa')
                        .exclude(original_language__iexact='per')
                        .exclude(original_language__iexact='fas')
                        .exclude(countries__code__iexact='IR')
                        .distinct()
                        .iterator(chunk_size=200)
                    )
                    if should_crawl(m)
                ]
                candidates.sort(key=crawl_priority)
                if limit is not None:
                    candidates = candidates[:limit]
                for movie in candidates:
                    stats['movies_scanned'] += 1
                    label = movie.original_title or movie.title
                    notify('movie_crawl', label)
                    if dry_run:
                        continue
                    had_links = _has_download_links(movie)
                    try:
                        result = _crawl_movie_links(
                            movie, connector, replace=True, resolve_english=False,
                        )
                    except ProviderRateLimited:
                        stats['movies_rate_limited'] += 1
                        stats['errors'].append({'type': 'movie', 'id': movie.id, 'code': 'rate_limited'})
                        time.sleep(30)
                        continue

                    movie.refresh_from_db()
                    coverage = _version_coverage(movie)
                    if coverage['has_dub']:
                        stats['movies_with_dub'] += 1
                    if coverage['has_sub']:
                        stats['movies_with_sub'] += 1
                    if coverage['has_both']:
                        stats['movies_with_both'] += 1

                    status = result.get('status')
                    imported = int(result.get('imported_count') or 0)
                    if status == 'ok' and imported > 0 and _has_download_links(movie):
                        stats['movies_crawled_ok'] += 1
                    elif maybe_delete(
                        obj=movie, label=label, had_links=had_links,
                        result=result, content_type='movie',
                    ):
                        stats['movies_deleted'] += 1
                    else:
                        stats['movies_errors'] += 1
                        stats['errors'].append({'type': 'movie', 'id': movie.id, **result})
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)

            if series:
                candidates = [
                    row for row in (
                        Series.objects.filter(is_published=True)
                        .exclude(original_language__iexact='fa')
                        .exclude(original_language__iexact='per')
                        .exclude(original_language__iexact='fas')
                        .exclude(countries__code__iexact='IR')
                        .distinct()
                        .iterator(chunk_size=200)
                    )
                    if should_crawl(row)
                ]
                candidates.sort(key=crawl_priority)
                if limit is not None:
                    candidates = candidates[:limit]
                for row in candidates:
                    stats['series_scanned'] += 1
                    label = row.original_title or row.title
                    notify('series_crawl', label)
                    if dry_run:
                        continue
                    had_links = _has_download_links(row)
                    try:
                        result = _crawl_series_links(
                            row, connector, replace=True, resolve_english=False,
                        )
                    except ProviderRateLimited:
                        stats['series_rate_limited'] += 1
                        stats['errors'].append({'type': 'series', 'id': row.id, 'code': 'rate_limited'})
                        time.sleep(30)
                        continue

                    row.refresh_from_db()
                    coverage = _version_coverage(row)
                    if coverage['has_dub']:
                        stats['series_with_dub'] += 1
                    if coverage['has_sub']:
                        stats['series_with_sub'] += 1
                    if coverage['has_both']:
                        stats['series_with_both'] += 1

                    status = result.get('status')
                    imported = int(result.get('imported_count') or 0)
                    if status == 'ok' and imported > 0 and _has_download_links(row):
                        stats['series_crawled_ok'] += 1
                    elif maybe_delete(
                        obj=row, label=label, had_links=had_links,
                        result=result, content_type='series',
                    ):
                        stats['series_deleted'] += 1
                    else:
                        stats['series_errors'] += 1
                        stats['errors'].append({'type': 'series', 'id': row.id, **result})
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    return stats


def import_this_week_with_myf2m(
    *,
    days: int = 7,
    limit: int = 40,
    movies: bool = True,
    series: bool = True,
    delete_if_missing: bool = True,
    crawl_delay_seconds: float = 0.75,
    dry_run: bool = False,
    on_progress: Callable | None = None,
) -> dict:
    """Import TMDB titles released/aired this week; keep only myf2m-backed ones."""
    from apps.catalog.provider_import.registry import get_connector

    exclude_iranian = bool(getattr(settings, 'CATALOG_EXCLUDE_IRANIAN', True))
    stats = {
        'provider': 'myf2m',
        'week_movies_discovered': 0,
        'week_movies_imported': 0,
        'week_movies_kept': 0,
        'week_movies_deleted': 0,
        'week_movies_skipped_iranian': 0,
        'week_series_discovered': 0,
        'week_series_imported': 0,
        'week_series_kept': 0,
        'week_series_deleted': 0,
        'week_series_skipped_iranian': 0,
        'movies_rate_limited': 0,
        'series_rate_limited': 0,
        'errors': [],
    }
    client = configured_tmdb_client()
    until = date.today()
    since = until - timedelta(days=max(1, int(days)))

    connector = get_connector('myf2m')
    last_exc = None
    for attempt in range(1, 4):
        try:
            connector.authenticate()
            last_exc = None
            break
        except ProviderRateLimited as exc:
            last_exc = exc
            time.sleep(10 * attempt)
    if last_exc is not None:
        raise last_exc

    def notify(phase: str, label: str):
        if callable(on_progress):
            on_progress(phase, label, stats)

    try:
        with _suppress_provider_publish_signals():
            if movies:
                seen: set[int] = set()
                summaries = []

                def _add_movie(item):
                    tid = int(item['id'])
                    if tid in seen:
                        return
                    seen.add(tid)
                    summaries.append(item)

                # Prefer English / popular theatrical releases — obscure local titles
                # rarely have Film2Media download/stream links.
                for item in client.discover_movies(
                    released_from=since,
                    released_until=until,
                    max_pages=4,
                    sort_by='popularity.desc',
                    with_original_language='en',
                ):
                    _add_movie(item)
                for item in client.discover_movies(
                    released_from=since,
                    released_until=until,
                    max_pages=2,
                    sort_by='popularity.desc',
                ):
                    _add_movie(item)
                for item in client.now_playing_movies(max_pages=3):
                    release = str(item.get('release_date') or '')
                    if release and release < since.isoformat():
                        continue
                    _add_movie(item)
                for item in client.trending_movies(window='week', max_pages=3):
                    release = str(item.get('release_date') or '')
                    if release and release < since.isoformat():
                        continue
                    _add_movie(item)
                summaries = summaries[: max(1, int(limit))]

                for summary in summaries:
                    stats['week_movies_discovered'] += 1
                    tmdb_id = int(summary['id'])
                    label = summary.get('title') or summary.get('original_title') or str(tmdb_id)
                    notify('week_movie', label)
                    if dry_run:
                        continue
                    if exclude_iranian and is_iranian_tmdb_details(summary):
                        stats['week_movies_skipped_iranian'] += 1
                        continue
                    try:
                        details = client.movie_details(tmdb_id)
                        if exclude_iranian and is_iranian_tmdb_details(details):
                            stats['week_movies_skipped_iranian'] += 1
                            continue
                        with transaction.atomic():
                            movie, created, _published, _skipped = upsert_tmdb_movie(
                                details,
                                auto_publish=False,
                            )
                        if created:
                            stats['week_movies_imported'] += 1
                        movie.is_published = True
                        movie.publication_status = Movie.PublicationStatus.PUBLISHED
                        movie.save(update_fields=['is_published', 'publication_status', 'updated_at'])
                    except Exception as exc:
                        stats['errors'].append({'tmdb_id': tmdb_id, 'type': 'week_movie', 'error': str(exc)[:200]})
                        continue

                    try:
                        result = _crawl_movie_links(movie, connector, replace=True)
                    except ProviderRateLimited:
                        stats['movies_rate_limited'] += 1
                        time.sleep(30)
                        continue

                    movie.refresh_from_db()
                    if result.get('status') == 'ok' and _has_download_links(movie):
                        stats['week_movies_kept'] += 1
                    elif delete_if_missing:
                        movie.delete()
                        stats['week_movies_deleted'] += 1
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)

            if series:
                seen_s: set[int] = set()
                show_summaries = []

                def _add_series(item):
                    tid = int(item['id'])
                    if tid in seen_s:
                        return
                    seen_s.add(tid)
                    show_summaries.append(item)

                for item in client.discover_tv(
                    aired_from=since,
                    aired_until=until,
                    max_pages=4,
                    sort_by='popularity.desc',
                    with_original_language='en',
                ):
                    _add_series(item)
                for item in client.discover_tv(
                    aired_from=since,
                    aired_until=until,
                    max_pages=2,
                    sort_by='popularity.desc',
                ):
                    _add_series(item)
                for item in client.trending_tv(window='week', max_pages=3):
                    air = str(item.get('first_air_date') or '')
                    if air and air < since.isoformat():
                        continue
                    _add_series(item)
                show_summaries = show_summaries[: max(1, int(limit))]

                for summary in show_summaries:
                    stats['week_series_discovered'] += 1
                    tmdb_id = int(summary['id'])
                    label = summary.get('name') or summary.get('original_name') or str(tmdb_id)
                    notify('week_series', label)
                    if dry_run:
                        continue
                    if exclude_iranian and is_iranian_tmdb_details(summary):
                        stats['week_series_skipped_iranian'] += 1
                        continue
                    try:
                        details = client.tv_details(tmdb_id)
                        if exclude_iranian and is_iranian_tmdb_details(details):
                            stats['week_series_skipped_iranian'] += 1
                            continue
                        with transaction.atomic():
                            row, created = upsert_tmdb_series(details)
                        if created:
                            stats['week_series_imported'] += 1
                        if not row.is_published:
                            row.is_published = True
                            row.save(update_fields=['is_published', 'updated_at'])
                    except Exception as exc:
                        stats['errors'].append({'tmdb_id': tmdb_id, 'type': 'week_series', 'error': str(exc)[:200]})
                        continue

                    try:
                        result = _crawl_series_links(row, connector, replace=True)
                    except ProviderRateLimited:
                        stats['series_rate_limited'] += 1
                        time.sleep(30)
                        continue

                    row.refresh_from_db()
                    if result.get('status') == 'ok' and _has_download_links(row):
                        stats['week_series_kept'] += 1
                    elif delete_if_missing:
                        row.delete()
                        stats['week_series_deleted'] += 1
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    return stats
