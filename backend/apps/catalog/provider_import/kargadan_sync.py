"""Import movie/series download links from kargadanmovie.com into the catalog.

Kargadan addresses every title by its IMDb id (``/movies/tt…/``, ``/series/tt…/``),
so the page for a catalog row is computed, never searched for, and identity is an
exact id compare. Storage goes through :func:`apply_provider_download_links`, the
same guarded path as Film2Media and Dornatv.
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.catalog.models import Movie, ProviderSource, Series
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.provider_import.link_apply import apply_provider_download_links

logger = logging.getLogger(__name__)


def ensure_kargadan_provider() -> ProviderSource:
    provider, _ = ProviderSource.objects.update_or_create(
        slug='kargadan',
        defaults={
            'name': 'Kargadan Movie (kargadanmovie.com)',
            'provider_type': ProviderSource.ProviderType.COOKIE_SESSION,
            'base_url': getattr(settings, 'KARGADAN_BASE_URL', 'https://kargadanmovie.com'),
            'auth_type': ProviderSource.AuthType.COOKIE_SESSION,
            'is_active': True,
            'rate_limit_per_minute': getattr(settings, 'KARGADAN_RATE_LIMIT_PER_MINUTE', 20),
            'timeout_seconds': getattr(settings, 'KARGADAN_TIMEOUT_SECONDS', 30),
            'verify_ssl': getattr(settings, 'KARGADAN_VERIFY_SSL', True),
            'config': {
                'supports_movies': True,
                'supports_series': True,
                'public_downloads': False,
                'discovery': 'wp-sitemap',
                'identity': 'imdb_id_in_url',
                'theme': 'kargadanmovie',
            },
        },
    )
    return provider


def _crawl(obj, *, content_type: str) -> dict:
    from apps.catalog.provider_import.registry import get_connector

    imdb_id = str(getattr(obj, 'imdb_id', '') or '').strip().lower()
    if not imdb_id.startswith('tt'):
        raise ProviderImportError('Kargadan titles are matched by IMDb id; this row has none.',
                                  code='kargadan_imdb_required')
    from apps.catalog.provider_import.providers.kargadan import inventory_says_missing, session_blocker

    blocker = session_blocker()
    if blocker:
        raise ProviderImportError('Kargadan has no signed-in session to read links with.', code=blocker)
    if inventory_says_missing(imdb_id, content_type=content_type):
        raise ProviderImportError('Title is not on Kargadan.', code='kargadan_page_missing')
    ensure_kargadan_provider()
    connector = get_connector('kargadan')
    try:
        crawled = connector.crawl_download_links(imdb_id, content_type=content_type)
    except ProviderImportError:
        raise
    except Exception as exc:
        raise ProviderImportError(f'kargadan crawl failed: {exc}', code='kargadan_crawl_failed') from exc
    finally:
        connector.close()
    page_imdb = str(crawled.get('imdb_id') or '').lower()
    if page_imdb and page_imdb != imdb_id:
        raise ProviderImportError(
            f'Kargadan page is {page_imdb}, expected {imdb_id}.', code='kargadan_identity_mismatch',
        )
    if crawled.get('content_type') and crawled['content_type'] != content_type:
        raise ProviderImportError(
            f'Kargadan lists {imdb_id} as a {crawled["content_type"]}.', code='kargadan_identity_mismatch',
        )
    if not crawled.get('available_links'):
        raise ProviderImportError(
            crawled.get('message') or 'No download links on the Kargadan page.',
            code=crawled.get('code') or 'kargadan_links_empty',
        )
    return crawled


def crawl_kargadan_downloads_for_movie(
    *,
    movie: Movie,
    replace: bool = True,
    queue_softsub_extract: bool = True,
) -> dict:
    crawled = _crawl(movie, content_type='movie')
    applied = apply_provider_download_links(
        movie,
        crawled['available_links'],
        replace=replace,
        queue_softsub_extract=queue_softsub_extract,
        empty_code='kargadan_links_empty',
        empty_message='No usable Kargadan download links after normalization.',
    )
    return {
        'movie_id': movie.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imdb_id': movie.imdb_id,
        'imported_count': applied.get('imported_count', 0),
        'download_links': applied.get('download_links') or [],
        'video_url': movie.video_url,
        'is_dubbed': movie.is_dubbed,
        'has_subtitle': movie.has_subtitle,
        'code': 'ok',
        'provider': 'kargadan',
    }


def crawl_kargadan_downloads_for_series(
    *,
    series: Series,
    replace: bool = True,
    queue_softsub_extract: bool = True,
) -> dict:
    crawled = _crawl(series, content_type='series')
    applied = apply_provider_download_links(
        series,
        crawled['available_links'],
        replace=replace,
        queue_softsub_extract=queue_softsub_extract,
        empty_code='kargadan_links_empty',
        empty_message='No usable Kargadan download links after normalization.',
    )
    return {
        'series_id': series.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imdb_id': series.imdb_id,
        'imported_count': applied.get('imported_count', 0),
        'download_links': applied.get('download_links') or [],
        'is_dubbed': series.is_dubbed,
        'has_subtitle': series.has_subtitle,
        'code': 'ok',
        'provider': 'kargadan',
    }
