"""Multi-provider download crawl: Film2Media (myf2m) + Dornatv.

Always merges public download links from both sites so qualities / dub / softsub
coverage is as complete as possible without wiping either source's encodes.
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.exceptions import ProviderImportError

logger = logging.getLogger(__name__)

DEFAULT_LINK_PROVIDERS = ('myf2m', 'dornatv')


def catalog_link_providers() -> list[str]:
    """Ordered provider slugs used for catalog playback/download import."""
    raw = getattr(settings, 'CATALOG_LINK_PROVIDERS', None)
    if raw is None:
        primary = (getattr(settings, 'CATALOG_LINK_PROVIDER', 'myf2m') or 'myf2m').strip().lower()
        ordered = [primary]
        for slug in DEFAULT_LINK_PROVIDERS:
            if slug not in ordered:
                ordered.append(slug)
        return ordered
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(';', ',').split(',') if p.strip()]
    else:
        parts = [str(p).strip().lower() for p in (raw or []) if str(p).strip()]
    # Always keep both target sites when configured list is partial.
    ordered: list[str] = []
    for slug in parts:
        if slug and slug not in ordered:
            ordered.append(slug)
    for slug in DEFAULT_LINK_PROVIDERS:
        if slug not in ordered:
            ordered.append(slug)
    return ordered or list(DEFAULT_LINK_PROVIDERS)


def _crawl_one_movie(slug: str, movie: Movie, *, replace: bool, queue_softsub: bool) -> dict:
    if slug == 'myf2m':
        from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_movie
        return crawl_myf2m_downloads_for_movie(
            movie=movie, replace=replace, queue_softsub_extract=queue_softsub,
        )
    if slug == 'dornatv':
        from apps.catalog.provider_import.dornatv_sync import crawl_dornatv_downloads_for_movie
        return crawl_dornatv_downloads_for_movie(
            movie=movie, replace=replace, queue_softsub_extract=queue_softsub,
        )
    raise ProviderImportError(f'Unsupported link provider "{slug}".', code='provider_unsupported')


def _crawl_one_series(slug: str, series: Series, *, replace: bool, queue_softsub: bool) -> dict:
    if slug == 'myf2m':
        from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_series
        return crawl_myf2m_downloads_for_series(
            series=series, replace=replace, queue_softsub_extract=queue_softsub,
        )
    if slug == 'dornatv':
        from apps.catalog.provider_import.dornatv_sync import crawl_dornatv_downloads_for_series
        return crawl_dornatv_downloads_for_series(
            series=series, replace=replace, queue_softsub_extract=queue_softsub,
        )
    raise ProviderImportError(f'Unsupported link provider "{slug}".', code='provider_unsupported')


def crawl_catalog_downloads_for_movie(
    *,
    movie: Movie,
    replace: bool = True,
    queue_softsub_extract: bool = True,
    providers: list[str] | None = None,
) -> dict:
    """Crawl myf2m + dornatv and merge all download qualities onto the movie."""
    slugs = providers or catalog_link_providers()
    per_provider: dict[str, dict] = {}
    errors: list[dict] = []
    imported_total = 0
    any_ok = False

    for index, slug in enumerate(slugs):
        # First successful provider may replace; later providers always merge.
        use_replace = bool(replace) and not any_ok
        queue_now = False
        try:
            result = _crawl_one_movie(
                slug, movie, replace=use_replace, queue_softsub=queue_now,
            )
            movie.refresh_from_db()
            any_ok = True
            imported_total = len([
                item for item in (movie.download_links or [])
                if isinstance(item, dict) and (
                    str(item.get('url') or '').strip() or str(item.get('key') or '').strip()
                )
            ])
            per_provider[slug] = {
                'status': 'ok',
                'imported_count': result.get('imported_count', 0),
                'page_path': result.get('page_path') or '',
                'page_url': result.get('page_url') or '',
            }
        except ProviderImportError as exc:
            per_provider[slug] = {
                'status': 'skipped',
                'code': getattr(exc, 'code', '') or '',
                'detail': str(exc)[:200],
            }
            errors.append({'provider': slug, 'code': getattr(exc, 'code', ''), 'detail': str(exc)[:200]})
            logger.info('multi-provider movie crawl %s skipped for %s: %s', slug, movie.pk, exc)
        except Exception as exc:
            per_provider[slug] = {'status': 'error', 'detail': str(exc)[:200]}
            errors.append({'provider': slug, 'detail': str(exc)[:200]})
            logger.exception('multi-provider movie crawl %s failed for %s', slug, movie.pk)

    if not any_ok:
        raise ProviderImportError(
            'No download links found on myf2m or dornatv.',
            code='catalog_links_empty',
        )

    if queue_softsub_extract:
        try:
            from apps.catalog.tasks import enqueue_movie_softsub
            enqueue_movie_softsub(movie.pk, force=not bool(movie.subtitle_tracks))
        except Exception:
            logger.exception('failed to queue softsub after multi crawl movie %s', movie.pk)

    return {
        'movie_id': movie.id,
        'imported_count': imported_total,
        'download_links': movie.download_links or [],
        'video_url': movie.video_url,
        'is_dubbed': movie.is_dubbed,
        'has_subtitle': movie.has_subtitle,
        'providers': per_provider,
        'errors': errors,
        'code': 'ok',
    }


def crawl_catalog_downloads_for_series(
    *,
    series: Series,
    replace: bool = True,
    queue_softsub_extract: bool = True,
    providers: list[str] | None = None,
) -> dict:
    """Crawl myf2m + dornatv and merge all download qualities onto the series."""
    slugs = providers or catalog_link_providers()
    per_provider: dict[str, dict] = {}
    errors: list[dict] = []
    imported_total = 0
    any_ok = False

    for index, slug in enumerate(slugs):
        use_replace = bool(replace) and not any_ok
        queue_now = False
        try:
            result = _crawl_one_series(
                slug, series, replace=use_replace, queue_softsub=queue_now,
            )
            series.refresh_from_db()
            any_ok = True
            imported_total = len([
                item for item in (series.download_links or [])
                if isinstance(item, dict) and (
                    str(item.get('url') or '').strip() or str(item.get('key') or '').strip()
                )
            ])
            per_provider[slug] = {
                'status': 'ok',
                'imported_count': result.get('imported_count', 0),
                'page_path': result.get('page_path') or '',
                'page_url': result.get('page_url') or '',
            }
        except ProviderImportError as exc:
            per_provider[slug] = {
                'status': 'skipped',
                'code': getattr(exc, 'code', '') or '',
                'detail': str(exc)[:200],
            }
            errors.append({'provider': slug, 'code': getattr(exc, 'code', ''), 'detail': str(exc)[:200]})
            logger.info('multi-provider series crawl %s skipped for %s: %s', slug, series.pk, exc)
        except Exception as exc:
            per_provider[slug] = {'status': 'error', 'detail': str(exc)[:200]}
            errors.append({'provider': slug, 'detail': str(exc)[:200]})
            logger.exception('multi-provider series crawl %s failed for %s', slug, series.pk)

    if not any_ok:
        raise ProviderImportError(
            'No download links found on myf2m or dornatv.',
            code='catalog_links_empty',
        )

    series.refresh_from_db(fields=['download_links'])
    try:
        from apps.catalog.subtitle_extract import ensure_episodes_from_download_links
        ensure_episodes_from_download_links(series)
    except Exception:
        logger.exception('failed final episode sync after multi crawl series %s', series.pk)

    if queue_softsub_extract:
        try:
            from apps.catalog.tasks import enqueue_series_softsub
            enqueue_series_softsub(series.pk, force=False, episode_limit=40)
        except Exception:
            logger.exception('failed to queue softsub after multi crawl series %s', series.pk)

    return {
        'series_id': series.id,
        'imported_count': imported_total,
        'download_links': series.download_links or [],
        'is_dubbed': series.is_dubbed,
        'has_subtitle': series.has_subtitle,
        'providers': per_provider,
        'errors': errors,
        'code': 'ok',
    }


def enrich_with_other_providers(
    obj,
    *,
    already_used: str,
    queue_softsub_extract: bool = True,
) -> dict:
    """Merge links from the other catalog providers without replacing existing rows."""
    others = [slug for slug in catalog_link_providers() if slug != (already_used or '').strip().lower()]
    if not others:
        return {'status': 'noop', 'providers': {}}
    if isinstance(obj, Movie):
        return crawl_catalog_downloads_for_movie(
            movie=obj,
            replace=False,
            queue_softsub_extract=queue_softsub_extract,
            providers=others,
        )
    return crawl_catalog_downloads_for_series(
        series=obj,
        replace=False,
        queue_softsub_extract=queue_softsub_extract,
        providers=others,
    )
