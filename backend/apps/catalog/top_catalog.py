"""Import TMDB top-rated movies/series and attach provider playback/download links."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save

from apps.catalog.models import Movie, Series
from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
from apps.catalog.tmdb import configured_tmdb_client

logger = logging.getLogger(__name__)


def _link_provider_slug() -> str:
    """Primary slug for logs; crawls always use catalog_link_providers()."""
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers
    providers = catalog_link_providers()
    return providers[0] if providers else 'myf2m'


def _link_providers() -> list[str]:
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers
    return catalog_link_providers()


def _has_download_links(obj) -> bool:
    from apps.catalog.provider_import.media_links import is_playable_video_link

    for item in (getattr(obj, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        if is_playable_video_link(item) or str(item.get('key') or '').strip():
            return True
    return False


def _version_coverage(obj) -> dict:
    """Report dub / soft / hard / toggleable SoftSub coverage from the same classifiers."""
    from apps.catalog.subtitle_extract import (
        download_links_imply_dub,
        download_links_imply_hardsub,
        download_links_imply_softsub,
        download_links_imply_subtitle,
    )

    links = getattr(obj, 'download_links', None) or []
    has_dub = download_links_imply_dub(links)
    has_soft = download_links_imply_softsub(links)
    has_hard = download_links_imply_hardsub(links)
    has_sub = download_links_imply_subtitle(links)
    tracks = getattr(obj, 'subtitle_tracks', None) or []
    has_tracks = any(
        isinstance(track, dict) and str(track.get('src') or track.get('key') or '').strip()
        for track in tracks
    )
    # Series SoftSub cues live on episodes, not the series row.
    if not has_tracks and hasattr(obj, 'seasons'):
        try:
            from apps.catalog.models import Episode
            has_tracks = Episode.objects.filter(
                season__series_id=obj.pk,
                is_published=True,
            ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()
        except Exception:
            has_tracks = False
    if not has_sub and has_tracks:
        has_sub = True
    has_toggleable = has_soft or has_tracks
    return {
        'has_links': _has_download_links(obj),
        'has_dub': has_dub,
        'has_softsub': has_soft,
        'has_hardsub': has_hard,
        'has_sub': has_sub,
        'has_toggleable_sub': has_toggleable,
        'has_tracks': has_tracks,
        # «both» = Persian dub + any subtitle encode (soft or hard) or extracted tracks.
        'has_both': has_dub and has_sub,
        # Preferred playback readiness: dub + toggleable SoftSub cues when possible.
        'has_playback_ready': has_dub and has_toggleable,
    }

def _publish_movie(movie: Movie) -> bool:
    if movie.is_published and movie.publication_status == Movie.PublicationStatus.PUBLISHED:
        return False
    from apps.catalog.provider_import.media_links import is_playable_video_url
    if not _has_download_links(movie) and not is_playable_video_url(movie.video_url):
        logger.warning('Refusing to publish movie %s without a valid playback source', movie.pk)
        return False
    movie.is_published = True
    movie.publication_status = Movie.PublicationStatus.PUBLISHED
    movie.save(update_fields=['is_published', 'publication_status', 'updated_at'])
    return True


def _publish_series(series: Series) -> bool:
    if series.is_published:
        return False
    if not _has_download_links(series):
        logger.warning('Refusing to publish series %s without valid episode playback links', series.pk)
        return False
    series.is_published = True
    series.save(update_fields=['is_published', 'updated_at'])
    return True


@contextmanager
def _suppress_provider_publish_signals():
    from apps.catalog.provider_import.signals import (
        auto_crawl_on_movie_publish,
        auto_crawl_on_series_publish,
    )

    post_save.disconnect(dispatch_uid='provider_auto_crawl_on_movie_publish')
    post_save.disconnect(dispatch_uid='provider_auto_crawl_on_series_publish')
    try:
        yield
    finally:
        post_save.connect(
            auto_crawl_on_movie_publish,
            sender=Movie,
            dispatch_uid='provider_auto_crawl_on_movie_publish',
        )
        post_save.connect(
            auto_crawl_on_series_publish,
            sender=Series,
            dispatch_uid='provider_auto_crawl_on_series_publish',
        )


def _extra_search_titles(obj) -> list[str]:
    """Collect alternate Latin titles (TMDB EN / metadata) for provider search."""
    out: list[str] = []
    meta = getattr(obj, 'source_metadata', None) or {}
    if isinstance(meta, dict):
        for key in ('english_title', 'title_en', 'name'):
            text = str(meta.get(key) or '').strip()
            # Skip non-title blobs (taglines/overviews) and ultra-long strings.
            if not text or len(text) > 120 or text.count(' ') > 14:
                continue
            if text and text not in out:
                out.append(text)
        alts = meta.get('alternative_titles') or meta.get('aka') or []
        if isinstance(alts, list):
            for item in alts[:8]:
                if isinstance(item, dict):
                    text = str(item.get('title') or item.get('name') or '').strip()
                else:
                    text = str(item or '').strip()
                if not text or len(text) > 120:
                    continue
                if text and text not in out:
                    out.append(text)
    return out


def _english_title_from_tmdb(obj, *, content_type: str) -> str:
    """Best-effort English display title from TMDB (bypass fa localization wrapper)."""
    tmdb_id = getattr(obj, 'tmdb_id', None)
    if not tmdb_id:
        return ''
    try:
        from apps.catalog.tmdb import configured_tmdb_client
        client = configured_tmdb_client()
        if content_type == 'series':
            details = client._request(f'tv/{int(tmdb_id)}', language='en-US')
            return str((details or {}).get('name') or '').strip()
        details = client._request(f'movie/{int(tmdb_id)}', language='en-US')
        return str((details or {}).get('title') or '').strip()
    except Exception:
        return ''


def _fast_provider_path(connector, *, title: str, original_title: str, year, content_type: str, extra_titles: list[str] | None = None) -> str:
    """Resolve a provider detail path using connector search (slug probe + query)."""
    titles = []
    for value in (original_title, title, *(extra_titles or [])):
        text = str(value or '').strip()
        if text and text not in titles:
            titles.append(text)
    query = {
        'title': title,
        'original_title': original_title or (titles[0] if titles else ''),
        'year': year,
        'titles': titles,
    }
    search = getattr(connector, f'search_{content_type}', None)
    if callable(search):
        try:
            hits = search(query) or []
            if hits:
                return hits[0].provider_item_id
        except Exception:
            logger.exception('Provider search failed for %s', original_title or title)
            return ''
    # Fallback for connectors that only expose slug probes.
    probe = getattr(connector, '_search_via_slug_probes', None)
    if not callable(probe):
        return ''
    try:
        hits = probe(query, content_type=content_type) or []
    except Exception:
        logger.exception('Provider slug probe failed for %s', original_title or title)
        return ''
    return hits[0].provider_item_id if hits else ''


def _crawl_movie_links(movie: Movie, connector=None, *, replace: bool = True, resolve_english: bool = True) -> dict:
    """Crawl Film2Media + Dornatv and merge all qualities/links."""
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import crawl_catalog_downloads_for_movie

    if _has_download_links(movie) and not replace:
        return {'status': 'skipped_has_links'}

    try:
        result = crawl_catalog_downloads_for_movie(
            movie=movie,
            replace=replace,
            queue_softsub_extract=True,
        )
        return {
            'status': 'ok',
            'imported_count': result.get('imported_count', 0),
            'page_path': (result.get('providers') or {}).get('myf2m', {}).get('page_path')
            or (result.get('providers') or {}).get('dornatv', {}).get('page_path'),
            'providers': result.get('providers') or {},
        }
    except ProviderImportError as exc:
        return {'status': 'error', 'code': getattr(exc, 'code', ''), 'detail': str(exc)[:200]}


def _crawl_series_links(series: Series, connector=None, *, replace: bool = True, resolve_english: bool = True) -> dict:
    """Crawl Film2Media + Dornatv and merge all qualities/links."""
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import crawl_catalog_downloads_for_series

    if _has_download_links(series) and not replace:
        return {'status': 'skipped_has_links'}

    try:
        result = crawl_catalog_downloads_for_series(
            series=series,
            replace=replace,
            queue_softsub_extract=True,
        )
        return {
            'status': 'ok',
            'imported_count': result.get('imported_count', 0),
            'page_path': (result.get('providers') or {}).get('myf2m', {}).get('page_path')
            or (result.get('providers') or {}).get('dornatv', {}).get('page_path'),
            'providers': result.get('providers') or {},
        }
    except ProviderImportError as exc:
        return {'status': 'error', 'code': getattr(exc, 'code', ''), 'detail': str(exc)[:200]}


def _record_crawl(stats: dict, *, content_type: str, crawl_result: dict, error_context: dict | None = None, obj=None):
    prefix = 'movies' if content_type == 'movie' else 'series'
    if crawl_result.get('status') == 'ok' and crawl_result.get('imported_count', 0) > 0:
        stats[f'{prefix}_crawled_ok'] += 1
    elif crawl_result.get('status') in {'page_not_found', 'skipped_has_links'}:
        stats[f'{prefix}_crawl_skipped'] += 1
    else:
        stats[f'{prefix}_crawl_failed'] += 1
        if error_context:
            stats['errors'].append({**error_context, **crawl_result})
    if obj is not None:
        coverage = _version_coverage(obj)
        if coverage['has_dub']:
            stats[f'{prefix}_with_dub'] += 1
        if coverage['has_sub']:
            stats[f'{prefix}_with_sub'] += 1
        if coverage['has_both']:
            stats[f'{prefix}_with_both'] += 1
        crawl_result['version_coverage'] = coverage


def import_top_catalog(
    *,
    limit: int = 250,
    import_movies: bool = True,
    import_series: bool = True,
    publish: bool = True,
    crawl: bool = True,
    crawl_only: bool = False,
    replace_links: bool = True,
    skip_existing_links: bool = True,
    skip_existing_titles: bool = False,
    require_provider_links: bool | None = None,
    crawl_delay_seconds: float = 0.0,
    source: str = 'popular',
    on_progress=None,
) -> dict:
    """Import TMDB popular/top-rated or IMDb Top-250 titles, publish, and crawl links.

    skip_existing_titles: leave catalog rows that already have this TMDB id untouched.
    require_provider_links: delete newly created rows that never
    got provider download links (also respects CATALOG_DELETE_WHEN_PROVIDER_MISSING).
    """
    client = configured_tmdb_client()
    source = (source or 'popular').strip().lower()
    if source not in {'popular', 'top_rated', 'imdb_top'}:
        source = 'popular'
    provider_slug = _link_provider_slug()
    exclude_iranian = bool(getattr(settings, 'CATALOG_EXCLUDE_IRANIAN', True))
    if require_provider_links is None:
        require_provider_links = bool(
            getattr(settings, 'CATALOG_DELETE_WHEN_PROVIDER_MISSING', True)
        )
    stats = {
        'source': source,
        'link_provider': provider_slug,
        'movies_discovered': 0,
        'movies_created': 0,
        'movies_updated': 0,
        'movies_skipped_existing': 0,
        'movies_skipped_iranian': 0,
        'movies_published': 0,
        'movies_crawled_ok': 0,
        'movies_crawl_skipped': 0,
        'movies_crawl_failed': 0,
        'movies_removed_no_links': 0,
        'movies_with_dub': 0,
        'movies_with_sub': 0,
        'movies_with_both': 0,
        'series_discovered': 0,
        'series_created': 0,
        'series_updated': 0,
        'series_skipped_existing': 0,
        'series_skipped_iranian': 0,
        'series_published': 0,
        'series_crawled_ok': 0,
        'series_crawl_skipped': 0,
        'series_crawl_failed': 0,
        'series_removed_no_links': 0,
        'series_with_dub': 0,
        'series_with_sub': 0,
        'series_with_both': 0,
        'errors': [],
    }

    connector = None
    if crawl:
        from apps.catalog.provider_import.registry import get_connector
        from apps.catalog.provider_import.exceptions import ProviderRateLimited

        connector = get_connector(provider_slug)
        # Providers can rate-limit bursts even during auth/validate; retry with backoff.
        last_exc = None
        for attempt in range(1, 4):
            try:
                connector.authenticate()
                last_exc = None
                break
            except ProviderRateLimited as exc:
                last_exc = exc
                sleep_seconds = 20 * attempt
                logger.warning(
                    '%s authenticate rate-limited (attempt %s/3): %s; sleeping %ss',
                    provider_slug, attempt, exc, sleep_seconds,
                )
                time.sleep(sleep_seconds)
        if last_exc is not None:
            raise last_exc

    def _notify(phase: str, label: str):
        if callable(on_progress):
            on_progress(phase, label, stats)

    def _imdb_movie_summaries():
        from apps.catalog.imdb_charts import imdb_top_movies

        for chart in imdb_top_movies(limit=limit):
            hit = client.resolve_imdb_to_tmdb(chart.imdb_id, content_type='movie')
            if not hit:
                stats['errors'].append({
                    'imdb_id': chart.imdb_id,
                    'type': 'movie',
                    'error': 'tmdb_find_miss',
                    'title': chart.primary_title,
                })
                continue
            hit = dict(hit)
            hit['imdb_id'] = chart.imdb_id
            hit['imdb_rank'] = chart.rank
            hit['imdb_rating'] = chart.average_rating
            yield hit

    def _imdb_series_summaries():
        from apps.catalog.imdb_charts import imdb_top_series

        for chart in imdb_top_series(limit=limit):
            hit = client.resolve_imdb_to_tmdb(chart.imdb_id, content_type='series')
            if not hit:
                stats['errors'].append({
                    'imdb_id': chart.imdb_id,
                    'type': 'series',
                    'error': 'tmdb_find_miss',
                    'title': chart.primary_title,
                })
                continue
            hit = dict(hit)
            hit['imdb_id'] = chart.imdb_id
            hit['imdb_rank'] = chart.rank
            hit['imdb_rating'] = chart.average_rating
            yield hit

    def _movie_summaries():
        if source == 'imdb_top':
            return _imdb_movie_summaries()
        if source == 'top_rated':
            return client.top_rated_movies(limit=limit)
        return client.popular_movies(limit=limit)

    def _series_summaries():
        if source == 'imdb_top':
            return _imdb_series_summaries()
        if source == 'top_rated':
            return client.top_rated_tv(limit=limit)
        return client.popular_tv(limit=limit)

    try:
        with _suppress_provider_publish_signals():
            if crawl_only:
                if import_movies:
                    movies = list(
                        Movie.objects.filter(is_published=True)
                        .exclude(original_language__iexact='fa')
                        .exclude(original_language__iexact='per')
                        .exclude(original_language__iexact='fas')
                        .exclude(countries__code__iexact='IR')
                        .distinct()
                        .order_by('-popularity', '-id')[: max(limit * 3, limit)]
                    )
                    if skip_existing_links and not replace_links:
                        # Revisit titles missing links OR missing dub/sub so the player can offer both.
                        movies = [
                            m for m in movies
                            if (not _has_download_links(m)) or (not _version_coverage(m)['has_both'])
                        ]
                    for movie in movies[:limit]:
                        if exclude_iranian and is_iranian_catalog_item(movie):
                            stats['movies_skipped_iranian'] += 1
                            continue
                        coverage = _version_coverage(movie)
                        if skip_existing_links and coverage['has_both'] and not replace_links:
                            stats['movies_crawl_skipped'] += 1
                            stats['movies_with_dub'] += 1
                            stats['movies_with_sub'] += 1
                            stats['movies_with_both'] += 1
                            continue
                        stats['movies_discovered'] += 1
                        _notify('movie_crawl', movie.title)
                        crawl_result = _crawl_movie_links(
                            movie,
                            connector,
                            replace=replace_links or not coverage['has_both'],
                        )
                        _record_crawl(stats, content_type='movie', crawl_result=crawl_result, obj=movie)
                        if require_provider_links and (
                            crawl_result.get('status') == 'page_not_found'
                            or crawl_result.get('code') in {
                                'myf2m_page_required', 'myf2m_links_empty',
                            }
                        ):
                            label = movie.title
                            movie.delete()
                            stats['movies_removed_no_links'] += 1
                            _notify('movie_removed_no_links', label)
                        if crawl_delay_seconds > 0:
                            time.sleep(crawl_delay_seconds)

                if import_series:
                    series_rows = list(
                        Series.objects.filter(is_published=True)
                        .exclude(original_language__iexact='fa')
                        .exclude(original_language__iexact='per')
                        .exclude(original_language__iexact='fas')
                        .exclude(countries__code__iexact='IR')
                        .distinct()
                        .order_by('-popularity', '-id')[: max(limit * 3, limit)]
                    )
                    if skip_existing_links and not replace_links:
                        series_rows = [
                            s for s in series_rows
                            if (not _has_download_links(s)) or (not _version_coverage(s)['has_both'])
                        ]
                    for series in series_rows[:limit]:
                        if exclude_iranian and is_iranian_catalog_item(series):
                            stats['series_skipped_iranian'] += 1
                            continue
                        coverage = _version_coverage(series)
                        if skip_existing_links and coverage['has_both'] and not replace_links:
                            stats['series_crawl_skipped'] += 1
                            stats['series_with_dub'] += 1
                            stats['series_with_sub'] += 1
                            stats['series_with_both'] += 1
                            continue
                        stats['series_discovered'] += 1
                        _notify('series_crawl', series.title)
                        crawl_result = _crawl_series_links(
                            series,
                            connector,
                            replace=replace_links or not coverage['has_both'],
                        )
                        _record_crawl(stats, content_type='series', crawl_result=crawl_result, obj=series)
                        if require_provider_links and (
                            crawl_result.get('status') == 'page_not_found'
                            or crawl_result.get('code') in {
                                'myf2m_page_required', 'myf2m_links_empty',
                            }
                        ):
                            series.delete()
                            stats['series_removed_no_links'] += 1
                            _notify('series_removed_no_links', series.title)
                        if crawl_delay_seconds > 0:
                            time.sleep(crawl_delay_seconds)
                return stats

            if import_movies:
                existing_movie_ids = set(
                    Movie.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True)
                ) if skip_existing_titles else set()
                for summary in _movie_summaries():
                    stats['movies_discovered'] += 1
                    tmdb_id = int(summary['id'])
                    label = summary.get('title') or summary.get('original_title') or str(tmdb_id)
                    if skip_existing_titles and tmdb_id in existing_movie_ids:
                        stats['movies_skipped_existing'] += 1
                        _notify('movie_skip_existing', label)
                        continue
                    if exclude_iranian and is_iranian_tmdb_details(summary):
                        stats['movies_skipped_iranian'] += 1
                        _notify('movie_skip_iranian', label)
                        continue
                    _notify('movie_import', label)
                    created = False
                    try:
                        details = client.movie_details(tmdb_id)
                        if exclude_iranian and is_iranian_tmdb_details(details):
                            stats['movies_skipped_iranian'] += 1
                            _notify('movie_skip_iranian', label)
                            continue
                        with transaction.atomic():
                            movie, created, _published, _skipped = upsert_tmdb_movie(
                                details,
                                auto_publish=False,
                            )
                        stats['movies_created' if created else 'movies_updated'] += 1
                        if created:
                            existing_movie_ids.add(tmdb_id)
                    except Exception as exc:
                        stats['errors'].append({'tmdb_id': tmdb_id, 'type': 'movie', 'error': str(exc)[:300]})
                        logger.exception('Failed to import movie tmdb_id=%s', tmdb_id)
                        continue

                    if publish and _publish_movie(movie):
                        stats['movies_published'] += 1

                    if not crawl or connector is None:
                        continue
                    coverage = _version_coverage(movie)
                    if skip_existing_links and coverage['has_both']:
                        stats['movies_crawl_skipped'] += 1
                        stats['movies_with_dub'] += 1
                        stats['movies_with_sub'] += 1
                        stats['movies_with_both'] += 1
                        continue

                    _notify('movie_crawl', label)
                    crawl_result = _crawl_movie_links(
                        movie,
                        connector,
                        replace=replace_links or not coverage['has_both'],
                    )
                    _record_crawl(
                        stats,
                        content_type='movie',
                        crawl_result=crawl_result,
                        error_context={'tmdb_id': tmdb_id, 'type': 'movie_crawl', 'title': label},
                        obj=movie,
                    )
                    if require_provider_links and (
                        (created and not _has_download_links(movie))
                        or crawl_result.get('status') == 'page_not_found'
                        or crawl_result.get('code') in {
                            'myf2m_page_required', 'myf2m_links_empty',
                        }
                    ):
                        movie.delete()
                        stats['movies_removed_no_links'] += 1
                        if created:
                            stats['movies_created'] = max(0, stats['movies_created'] - 1)
                        existing_movie_ids.discard(tmdb_id)
                        _notify('movie_removed_no_links', label)
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)

            if import_series:
                existing_series_ids = set(
                    Series.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True)
                ) if skip_existing_titles else set()
                for summary in _series_summaries():
                    stats['series_discovered'] += 1
                    tmdb_id = int(summary['id'])
                    label = summary.get('name') or summary.get('original_name') or str(tmdb_id)
                    if skip_existing_titles and tmdb_id in existing_series_ids:
                        stats['series_skipped_existing'] += 1
                        _notify('series_skip_existing', label)
                        continue
                    if exclude_iranian and is_iranian_tmdb_details(summary):
                        stats['series_skipped_iranian'] += 1
                        _notify('series_skip_iranian', label)
                        continue
                    _notify('series_import', label)
                    created = False
                    try:
                        details = client.tv_details(tmdb_id)
                        if exclude_iranian and is_iranian_tmdb_details(details):
                            stats['series_skipped_iranian'] += 1
                            _notify('series_skip_iranian', label)
                            continue
                        with transaction.atomic():
                            series, created = upsert_tmdb_series(details)
                        stats['series_created' if created else 'series_updated'] += 1
                        if created:
                            existing_series_ids.add(tmdb_id)
                    except Exception as exc:
                        stats['errors'].append({'tmdb_id': tmdb_id, 'type': 'series', 'error': str(exc)[:300]})
                        logger.exception('Failed to import series tmdb_id=%s', tmdb_id)
                        continue

                    if publish and _publish_series(series):
                        stats['series_published'] += 1

                    if not crawl or connector is None:
                        continue
                    coverage = _version_coverage(series)
                    if skip_existing_links and coverage['has_both']:
                        stats['series_crawl_skipped'] += 1
                        stats['series_with_dub'] += 1
                        stats['series_with_sub'] += 1
                        stats['series_with_both'] += 1
                        continue

                    _notify('series_crawl', label)
                    crawl_result = _crawl_series_links(
                        series,
                        connector,
                        replace=replace_links or not coverage['has_both'],
                    )
                    _record_crawl(
                        stats,
                        content_type='series',
                        crawl_result=crawl_result,
                        error_context={'tmdb_id': tmdb_id, 'type': 'series_crawl', 'title': label},
                        obj=series,
                    )
                    if require_provider_links and (
                        (created and not _has_download_links(series))
                        or crawl_result.get('status') == 'page_not_found'
                        or crawl_result.get('code') in {
                            'myf2m_page_required', 'myf2m_links_empty',
                        }
                    ):
                        series.delete()
                        stats['series_removed_no_links'] += 1
                        if created:
                            stats['series_created'] = max(0, stats['series_created'] - 1)
                        existing_series_ids.discard(tmdb_id)
                        _notify('series_removed_no_links', label)
                    if crawl_delay_seconds > 0:
                        time.sleep(crawl_delay_seconds)
    finally:
        if connector is not None:
            close = getattr(connector, 'close', None)
            if callable(close):
                close()

    return stats
