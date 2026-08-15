"""Celery tasks for licensed provider import."""

import logging

from celery import shared_task

from apps.catalog.models import ProviderImportJob

from .catalog_lookup import run_catalog_discover_job
from .service import run_provider_import_job

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=110 * 60,
    time_limit=120 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_provider_import_job_task(self, job_id: str):
    job = ProviderImportJob.objects.filter(pk=job_id).only(
        'id', 'target_movie_id', 'target_series_id', 'provider_id',
    ).first()
    if job and (job.target_movie_id or job.target_series_id):
        return run_catalog_discover_job(job_id)
    return run_provider_import_job(job_id)


@shared_task(
    bind=True,
    max_retries=4,
    default_retry_delay=60,
    soft_time_limit=12 * 60,
    time_limit=15 * 60,
    acks_late=True,
)
def auto_crawl_myf2m_movie_downloads_task(self, movie_id: int, replace: bool = True):
    """Find myf2m + dornatv pages and merge public download links after publish."""
    from django.core.cache import cache

    from apps.catalog.models import Movie
    from .exceptions import ProviderImportError, ProviderRateLimited
    from .multi_provider_crawl import crawl_catalog_downloads_for_movie

    movie = Movie.objects.filter(pk=movie_id).first()
    if movie is None:
        return {'movie_id': movie_id, 'status': 'missing'}
    if not (movie.is_published or movie.publication_status == Movie.PublicationStatus.PUBLISHED):
        return {'movie_id': movie_id, 'status': 'not_published'}

    existing = [
        item for item in (movie.download_links or [])
        if isinstance(item, dict) and (str(item.get('url') or '').strip() or str(item.get('key') or '').strip())
    ]
    if existing and not replace:
        return {'movie_id': movie_id, 'status': 'already_has_links', 'imported_count': len(existing)}

    run_lock = f'myf2m-run-movie-{int(movie_id)}'
    if not cache.add(run_lock, self.request.id or '1', timeout=15 * 60):
        return {'movie_id': movie_id, 'status': 'already_running'}

    global_lock = 'myf2m-global-http'
    if not cache.add(global_lock, f'movie:{movie_id}', timeout=10 * 60):
        cache.delete(run_lock)
        raise self.retry(countdown=min(120, 30 * (self.request.retries + 1)))

    try:
        result = crawl_catalog_downloads_for_movie(movie=movie, replace=True)
    except ProviderRateLimited as exc:
        logger.warning('catalog auto-crawl rate-limited for movie %s; retrying', movie_id)
        raise self.retry(exc=exc, countdown=min(300, 60 * (self.request.retries + 1)))
    except ProviderImportError as exc:
        code = getattr(exc, 'code', '') or ''
        logger.info('catalog auto-crawl skipped for movie %s: %s (%s)', movie_id, exc, code)
        if self.request.retries < self.max_retries and code in {
            'catalog_links_empty', 'myf2m_links_empty', 'myf2m_crawl_failed', 'myf2m_page_required',
            'dornatv_links_empty', 'dornatv_crawl_failed', 'dornatv_page_required',
        }:
            raise self.retry(exc=exc, countdown=min(600, 120 * (self.request.retries + 1)))
        return {'movie_id': movie_id, 'status': 'skipped', 'code': code, 'detail': str(exc)[:300]}
    except Exception as exc:  # pragma: no cover
        logger.exception('catalog auto-crawl failed for movie %s', movie_id)
        raise self.retry(exc=exc)
    finally:
        cache.delete(global_lock)
        cache.delete(run_lock)

    logger.info(
        'catalog auto-crawl ok for movie %s imported=%s providers=%s',
        movie_id, result.get('imported_count'), list((result.get('providers') or {}).keys()),
    )
    return {
        'movie_id': movie_id,
        'status': 'ok',
        'imported_count': result.get('imported_count', 0),
        'providers': result.get('providers') or {},
    }


@shared_task(
    bind=True,
    max_retries=4,
    default_retry_delay=60,
    soft_time_limit=12 * 60,
    time_limit=15 * 60,
    acks_late=True,
)
def auto_crawl_myf2m_series_downloads_task(self, series_id: int, replace: bool = True):
    """Find myf2m + dornatv pages and merge public download links after publish."""
    from django.core.cache import cache

    from apps.catalog.models import Series
    from .exceptions import ProviderImportError, ProviderRateLimited
    from .multi_provider_crawl import crawl_catalog_downloads_for_series

    series = Series.objects.filter(pk=series_id).first()
    if series is None:
        return {'series_id': series_id, 'status': 'missing'}
    if not series.is_published:
        return {'series_id': series_id, 'status': 'not_published'}

    existing = [
        item for item in (series.download_links or [])
        if isinstance(item, dict) and (str(item.get('url') or '').strip() or str(item.get('key') or '').strip())
    ]
    if existing and not replace:
        return {'series_id': series_id, 'status': 'already_has_links', 'imported_count': len(existing)}

    run_lock = f'myf2m-run-series-{int(series_id)}'
    if not cache.add(run_lock, self.request.id or '1', timeout=15 * 60):
        return {'series_id': series_id, 'status': 'already_running'}

    global_lock = 'myf2m-global-http'
    if not cache.add(global_lock, f'series:{series_id}', timeout=10 * 60):
        cache.delete(run_lock)
        raise self.retry(countdown=min(120, 30 * (self.request.retries + 1)))

    try:
        result = crawl_catalog_downloads_for_series(series=series, replace=True)
    except ProviderRateLimited as exc:
        raise self.retry(exc=exc, countdown=min(300, 60 * (self.request.retries + 1)))
    except ProviderImportError as exc:
        code = getattr(exc, 'code', '') or ''
        logger.info('catalog auto-crawl skipped for series %s: %s (%s)', series_id, exc, code)
        if self.request.retries < self.max_retries and code in {
            'catalog_links_empty', 'myf2m_links_empty', 'myf2m_crawl_failed', 'myf2m_page_required',
            'dornatv_links_empty', 'dornatv_crawl_failed', 'dornatv_page_required',
        }:
            raise self.retry(exc=exc, countdown=min(600, 120 * (self.request.retries + 1)))
        return {'series_id': series_id, 'status': 'skipped', 'code': code, 'detail': str(exc)[:300]}
    except Exception as exc:  # pragma: no cover
        logger.exception('catalog auto-crawl failed for series %s', series_id)
        raise self.retry(exc=exc)
    finally:
        cache.delete(global_lock)
        cache.delete(run_lock)

    logger.info(
        'catalog auto-crawl ok for series %s imported=%s providers=%s',
        series_id, result.get('imported_count'), list((result.get('providers') or {}).keys()),
    )
    return {
        'series_id': series_id,
        'status': 'ok',
        'imported_count': result.get('imported_count', 0),
        'providers': result.get('providers') or {},
    }


@shared_task(
    bind=True,
    soft_time_limit=12 * 60,
    time_limit=15 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def import_missing_dornatv_task(self):
    """Always-on beat tick: import missing Dornatv titles with FA+EN + links + TMDB meta."""
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'DORNATV_IMPORT_ENABLED', True):
        return {'status': 'disabled'}

    lock = 'dornatv-import-missing-lock'
    if not cache.add(lock, self.request.id or '1', timeout=14 * 60):
        return {'status': 'already_running'}
    try:
        from .dornatv_import import run_dornatv_missing_import
        result = run_dornatv_missing_import()
        logger.info('dornatv missing-import tick: %s', result)
        return result
    finally:
        cache.delete(lock)
