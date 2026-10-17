"""Celery tasks for licensed provider import."""

import logging

from celery import shared_task

from apps.catalog.models import ProviderImportJob

from .catalog_lookup import run_catalog_discover_job
from .service import run_provider_import_job

logger = logging.getLogger(__name__)


@shared_task(bind=True, soft_time_limit=5 * 60 * 60, time_limit=6 * 60 * 60,
             acks_late=True, reject_on_worker_lost=True)
def run_catalog_year_import_task(self, job_id: str):
    """Run the discovery/enrichment pipeline as a cancellable admin job.

    Discovery covers every provider named in ``params['providers']`` (Dornatv and
    Film2Media by default), and ``params['year_start']``/``params['year_end']``
    narrow every phase to a release-year window — leave them unset to work the
    whole catalog.
    """
    from django.core.cache import cache
    from django.utils import timezone
    from .service import append_log

    lock = 'catalog-year-import-admin-lock'
    if not cache.add(lock, self.request.id or job_id, timeout=6 * 60 * 60):
        return {'status': 'already_running'}
    job = ProviderImportJob.objects.get(pk=job_id)
    params = job.params or {}

    def cancelled():
        return ProviderImportJob.objects.filter(pk=job_id, cancel_requested=True).exists()

    def progress(stats, label):
        ProviderImportJob.objects.filter(pk=job_id).update(
            current_item_label=label,
            processed_items=int(stats.get('movies_considered', 0)) + int(stats.get('series_considered', 0)),
            imported_files=int(stats.get('movies_crawled_ok', 0)) + int(stats.get('series_crawled_ok', 0)),
            failed_items=int(stats.get('movies_failed', 0)) + int(stats.get('series_failed', 0)),
        )

    try:
        job.status = ProviderImportJob.Status.RUNNING
        job.started_at = timezone.now()
        job.current_item_label = 'آماده‌سازی ایمپورت کاتالوگ'
        job.save(update_fields=['status', 'started_at', 'current_item_label', 'updated_at'])
        from scripts.import_2026_full import (
            phase_dornatv_missing,
            phase_enrich,
            phase_myf2m_missing,
            phase_softsub_queue,
            report,
        )
        ctype = params.get('content_type', 'both')
        movies = ctype in ('movies', 'both')
        series = ctype in ('series', 'both')
        # A missing/blank window means "all years"; the phases treat None as no filter.
        window = {
            'year_start': params.get('year_start') or None,
            'year_end': params.get('year_end') or None,
        }
        providers = [str(slug) for slug in (params.get('providers') or ['dornatv', 'myf2m'])]
        summary = {'before': report(**window), 'providers': providers, 'window': window}
        if params.get('discover', True):
            discovery = {}
            provider_phases = (
                ('dornatv', 'دورنا تی‌وی', phase_dornatv_missing, {
                    'rounds_key': 'dornatv_rounds', 'rounds_default': 8,
                    'movies_key': 'movies_per_round', 'movies_default': 40,
                    'series_key': 'series_per_round', 'series_default': 20,
                }),
                ('myf2m', 'فیلم تو مدیا', phase_myf2m_missing, {
                    'rounds_key': 'myf2m_rounds', 'rounds_default': 6,
                    'movies_key': 'myf2m_movies_per_round', 'movies_default': 25,
                    'series_key': 'myf2m_series_per_round', 'series_default': 12,
                }),
            )
            for slug, label, phase, keys in provider_phases:
                if slug not in providers or cancelled():
                    continue
                totals = {'movies_created': 0, 'series_created': 0, 'skipped_existing': 0, 'rounds': 0}
                extra = {}
                if slug == 'myf2m':
                    extra['pages_per_round'] = int(params.get('myf2m_pages_per_round') or 0) or None
                for round_no in range(int(params.get(keys['rounds_key'], keys['rounds_default']))):
                    if cancelled():
                        break
                    ProviderImportJob.objects.filter(pk=job_id).update(
                        current_item_label=f'کشف {label}: دور {round_no + 1}',
                    )
                    row = phase(
                        movies_limit=int(params.get(keys['movies_key'], keys['movies_default'])) if movies else 0,
                        series_limit=int(params.get(keys['series_key'], keys['series_default'])) if series else 0,
                        rounds=1, delay=float(params.get('delay', .35)), should_cancel=cancelled,
                        **extra, **window,
                    )
                    for key in totals:
                        totals[key] += int(row.get(key, 0))
                    append_log(job, 'info', f'دور کشف {label} {round_no + 1} تمام شد.', row)
                    if not row.get('movies_created') and not row.get('series_created'):
                        break
                discovery[slug] = totals
            # Keep the flat totals the admin UI already reads alongside the per-provider rows.
            discovery.update({
                key: sum(int(row.get(key, 0)) for row in discovery.values())
                for key in ('movies_created', 'series_created', 'skipped_existing', 'rounds')
            })
            summary['discover'] = discovery
        if params.get('enrich', True) and not cancelled():
            summary['enrich'] = phase_enrich(
                limit=int(params.get('enrich_limit') or 0) or None,
                delay=float(params.get('delay', .35)), movies=movies, series=series,
                should_cancel=cancelled, on_progress=progress, **window,
            )
        if params.get('softsub', True) and not cancelled():
            ProviderImportJob.objects.filter(pk=job_id).update(current_item_label='صف زیرنویس‌ها')
            summary['softsub'] = phase_softsub_queue(
                limit_movies=800 if movies else 0, limit_series=400 if series else 0, **window,
            )
        # Episodes come from provider links, so their titles/overviews/air dates
        # only exist after this TMDB season pass — run it inside the same job so
        # an admin import really does leave the catalog fully populated.
        if params.get('episode_metadata', True) and series and not cancelled():
            from apps.catalog.episode_metadata import complete_missing_episode_metadata
            ProviderImportJob.objects.filter(pk=job_id).update(
                current_item_label='تکمیل متادیتای فصل‌ها و قسمت‌ها',
            )
            summary['episode_metadata'] = complete_missing_episode_metadata(
                series_limit=int(params.get('episode_metadata_limit') or 0) or 400,
                stills=bool(params.get('episode_stills', False)),
                delay=float(params.get('delay', .35)),
                should_cancel=cancelled,
            )
            append_log(job, 'info', 'متادیتای قسمت‌ها تکمیل شد.', summary['episode_metadata'])
        summary['after'] = report(**window)
        job.refresh_from_db()
        job.checkpoint = summary
        job.finished_at = timezone.now()
        job.current_item_label = 'لغو شد' if cancelled() else 'ایمپورت تکمیل شد'
        job.status = ProviderImportJob.Status.CANCELLED if cancelled() else ProviderImportJob.Status.COMPLETED
        job.save(update_fields=['checkpoint', 'finished_at', 'current_item_label', 'status', 'updated_at'])
        append_log(job, 'warning' if cancelled() else 'info', job.current_item_label, summary)
        return summary
    except Exception as exc:
        logger.exception('catalog year import failed job=%s', job_id)
        ProviderImportJob.objects.filter(pk=job_id).update(
            status=ProviderImportJob.Status.FAILED, error_message=str(exc)[:500],
            sanitized_error_code='catalog_year_import_failed', finished_at=timezone.now(),
        )
        append_log(job, 'error', 'ایمپورت سالانه ناموفق بود.', {'error': str(exc)[:300]})
        raise
    finally:
        cache.delete(lock)


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
    soft_time_limit=50 * 60,
    time_limit=55 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def complete_episode_metadata_task(self, series_limit: int | None = None, stills: bool | None = None):
    """Fill season/episode metadata (real titles, overviews, air dates, runtimes).

    Episodes are materialised from provider download links, so without this pass
    they keep their stub «قسمت N» label and stay empty.
    """
    from django.core.cache import cache

    from apps.catalog.episode_metadata import complete_missing_episode_metadata

    lock = 'catalog-episode-metadata-lock'
    if not cache.add(lock, self.request.id or '1', timeout=55 * 60):
        return {'status': 'already_running'}
    try:
        result = complete_missing_episode_metadata(series_limit=series_limit, stills=stills)
        logger.info('episode metadata tick: %s', result)
        return result
    finally:
        cache.delete(lock)


# --- Discovery liveness -----------------------------------------------------
# The two tasks below are the archive's heartbeat: they are the only thing that
# finds titles the catalog does not have yet. Everything else refreshes what is
# already there. So "is the import running?" reduces to "did one of these finish
# recently?", and that question needs an answer that survives the worker, the
# beat and the broker all dying.
#
# Each completed run stamps a timestamp in the shared cache. ``import_watchdog_task``
# reads those stamps from the uncontended ``support`` lane and restarts whatever
# has gone quiet. A missing stamp is treated as stale on purpose: if the cache is
# ever cleared the watchdog starts an import, which is the safe direction to fail.
DISCOVERY_LANES = {
    'dornatv': {
        'lock': 'dornatv-import-missing-lock',
        'task': 'apps.catalog.provider_import.tasks.import_missing_dornatv_task',
        'enabled_setting': 'DORNATV_IMPORT_ENABLED',
    },
    'myf2m': {
        'lock': 'myf2m-import-missing-lock',
        'task': 'apps.catalog.provider_import.tasks.import_missing_myf2m_task',
        'enabled_setting': 'MYF2M_IMPORT_ENABLED',
    },
    # Sitemap-driven: new titles plus link refreshes for pages Kargadan edited.
    # Without a signed-in session it still completes (and refreshes the inventory),
    # so waiting on an operator never reads as a dead lane.
    'kargadan': {
        'lock': 'kargadan-import-missing-lock',
        'task': 'apps.catalog.provider_import.tasks.import_missing_kargadan_task',
        'enabled_setting': 'KARGADAN_IMPORT_ENABLED',
    },
    # Not discovery in the listing sense, but the same promise: the IMDb Top 250
    # shelf keeps filling itself. It has its own queue so it never waits behind
    # the listing walks or the per-title retry backlog.
    'top250': {
        'lock': 'top250-complete-lock',
        'task': 'apps.catalog.provider_import.tasks.complete_top250_task',
        'enabled_setting': 'CATALOG_TOP250_ENABLED',
        'queue': 'imports-top250',
    },
    # This week's trending and newest titles, hottest first. Its own queue, first
    # in the imports worker's -Q, so what people are looking for right now never
    # waits behind the Top 250 backlog, the listing walks or the retry pile.
    'hot': {
        'lock': 'hot-titles-complete-lock',
        'task': 'apps.catalog.provider_import.tasks.complete_hot_titles_task',
        'enabled_setting': 'CATALOG_HOT_ENABLED',
        'queue': 'imports-hot',
    },
}
DISCOVERY_HEARTBEAT_TTL = 24 * 60 * 60


def _discovery_heartbeat_key(lane: str) -> str:
    return f'catalog:import:last_success:{lane}'


def mark_discovery_alive(lane: str) -> None:
    """Record that ``lane`` *completed* a discovery run just now.

    Completed, not attempted. This is called on the success path only, and
    deliberately not from a ``finally``: stamping on the way out of a failed run
    makes a lane that fails every single time indistinguishable from a healthy one.
    That is not hypothetical — dornatv hit its soft time limit on every tick for
    hours, raised every time, imported nothing, and read as perfectly healthy to the
    watchdog because the stamp was in a ``finally``.

    Restarting a failing lane is the right response anyway: the walks are
    checkpointed, so a restart resumes rather than repeats, and the silence window
    is wide enough that a single bad tick never triggers one.
    """
    from django.core.cache import cache
    from django.utils import timezone

    cache.set(
        _discovery_heartbeat_key(lane),
        timezone.now().isoformat(),
        timeout=DISCOVERY_HEARTBEAT_TTL,
    )


def discovery_silent_minutes(lane: str):
    """Minutes since ``lane`` last finished, or ``None`` when it has never reported."""
    from django.core.cache import cache
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    raw = cache.get(_discovery_heartbeat_key(lane))
    if not raw:
        return None
    stamped = parse_datetime(raw) if isinstance(raw, str) else raw
    if stamped is None:
        return None
    return (timezone.now() - stamped).total_seconds() / 60.0


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
        mark_discovery_alive('dornatv')
        return result
    finally:
        cache.delete(lock)


@shared_task(
    bind=True,
    soft_time_limit=12 * 60,
    time_limit=15 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def import_missing_myf2m_task(self):
    """Always-on beat tick: import missing Film2Media titles the Dornatv walk never sees.

    Film2Media publishes titles Dornatv does not carry, so discovery has to walk
    both providers; this is the listing-driven twin of
    :func:`import_missing_dornatv_task`.
    """
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'MYF2M_IMPORT_ENABLED', True):
        return {'status': 'disabled'}

    lock = 'myf2m-import-missing-lock'
    if not cache.add(lock, self.request.id or '1', timeout=14 * 60):
        return {'status': 'already_running'}
    try:
        from .myf2m_discover import run_myf2m_missing_import
        result = run_myf2m_missing_import()
        logger.info('myf2m missing-import tick: %s', result)
        mark_discovery_alive('myf2m')
        return result
    finally:
        cache.delete(lock)


@shared_task(
    bind=True,
    soft_time_limit=12 * 60,
    time_limit=15 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def import_missing_kargadan_task(self):
    """Always-on beat tick: import Kargadan titles the catalog lacks, refresh edited pages.

    See :mod:`apps.catalog.provider_import.kargadan_import`.
    """
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'KARGADAN_IMPORT_ENABLED', True):
        return {'status': 'disabled'}

    lock = DISCOVERY_LANES['kargadan']['lock']
    if not cache.add(lock, self.request.id or '1', timeout=14 * 60):
        return {'status': 'already_running'}
    try:
        from .kargadan_import import run_kargadan_missing_import
        result = run_kargadan_missing_import()
        logger.info('kargadan missing-import tick: %s', result)
        mark_discovery_alive('kargadan')
        return result
    finally:
        cache.delete(lock)


@shared_task(
    bind=True,
    soft_time_limit=9 * 60,
    time_limit=11 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def fill_missing_sources_task(self):
    """Beat tick: ask the providers a published title has no links from yet.

    See :mod:`apps.catalog.provider_import.source_fill`.
    """
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'CATALOG_SOURCE_FILL_ENABLED', True):
        return {'status': 'disabled'}

    lock = 'catalog-source-fill-lock'
    if not cache.add(lock, self.request.id or '1', timeout=10 * 60):
        return {'status': 'already_running'}
    try:
        from .source_fill import run_source_fill
        result = run_source_fill()
        logger.info('source fill tick: %s', result)
        return result
    finally:
        cache.delete(lock)


@shared_task(
    bind=True,
    soft_time_limit=28 * 60,
    time_limit=30 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def complete_top250_task(self):
    """Always-on beat tick: make more IMDb Top 250 positions watchable, best rank first.

    This used to be one lane of the crawler loop, where it only ran after the
    ~17-minute listing walk and at most 20 positions a round, so the most visible
    shelf on the site and the app filled slowly and stalled whenever a single
    series crawl was killed. As its own lane it runs every 10 minutes on
    ``imports-top250``, ends itself within ``CATALOG_TOP250_BUDGET_SECONDS``, and
    is restarted by :func:`import_watchdog_task` like the discovery lanes.
    """
    import time as _time

    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'CATALOG_TOP250_ENABLED', True):
        return {'status': 'disabled'}

    lock = DISCOVERY_LANES['top250']['lock']
    if not cache.add(lock, self.request.id or '1', timeout=31 * 60):
        return {'status': 'already_running'}
    try:
        from apps.catalog.top250 import complete_chart, refresh_chart

        started = _time.monotonic()
        try:
            # A no-op unless the stored chart is older than the window; the
            # chart itself only changes daily.
            refresh_chart(max_age_hours=20)
        except Exception:  # a stale chart is still a chart worth completing
            logger.warning('top250 chart refresh failed; completing the stored chart', exc_info=True)
        budget = float(getattr(settings, 'CATALOG_TOP250_BUDGET_SECONDS', 20 * 60) or 20 * 60)
        result = complete_chart(
            limit=int(getattr(settings, 'CATALOG_TOP250_LIMIT', 40) or 40),
            retry_hours=float(getattr(settings, 'CATALOG_TOP250_RETRY_HOURS', 24) or 24),
            delay=float(getattr(settings, 'CATALOG_TOP250_DELAY_SECONDS', 1.0) or 0),
            budget_seconds=max(60.0, budget - (_time.monotonic() - started)),
        )
        logger.info('top250 completion tick: %s', {k: v for k, v in result.items() if k != 'errors'})
        mark_discovery_alive('top250')
        return result
    finally:
        cache.delete(lock)


@shared_task(
    bind=True,
    soft_time_limit=12 * 60,
    time_limit=14 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def complete_hot_titles_task(self):
    """Always-on beat tick: make this week's trending and newest titles watchable.

    Refreshes the TMDB hot chart when it is older than
    ``CATALOG_HOT_CHART_MAX_AGE_HOURS`` (a no-op otherwise), then completes up to
    ``CATALOG_HOT_LIMIT`` titles hottest first within
    ``CATALOG_HOT_BUDGET_SECONDS``. Runs every 10 minutes on ``imports-hot`` and
    is restarted by :func:`import_watchdog_task` like the other lanes.
    """
    import time as _time

    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'CATALOG_HOT_ENABLED', True):
        return {'status': 'disabled'}

    lock = DISCOVERY_LANES['hot']['lock']
    if not cache.add(lock, self.request.id or '1', timeout=15 * 60):
        return {'status': 'already_running'}
    try:
        from apps.catalog.hot_titles import complete_hot_titles, refresh_hot_chart

        started = _time.monotonic()
        try:
            chart = refresh_hot_chart()
        except Exception:  # a stored chart is still worth completing
            logger.warning('hot chart refresh failed; completing the stored chart', exc_info=True)
            chart = {'status': 'error'}
        budget = float(getattr(settings, 'CATALOG_HOT_BUDGET_SECONDS', 9 * 60) or 9 * 60)
        result = complete_hot_titles(
            limit=int(getattr(settings, 'CATALOG_HOT_LIMIT', 30) or 30),
            retry_hours=float(getattr(settings, 'CATALOG_HOT_RETRY_HOURS', 6) or 6),
            delay=float(getattr(settings, 'CATALOG_HOT_DELAY_SECONDS', 1.0) or 0),
            budget_seconds=max(60.0, budget - (_time.monotonic() - started)),
        )
        result['chart'] = chart.get('status')
        logger.info('hot titles tick: %s', {k: v for k, v in result.items() if k != 'errors'})
        mark_discovery_alive('hot')
        return result
    finally:
        cache.delete(lock)


@shared_task(name='apps.catalog.provider_import.tasks.import_watchdog_task')
def import_watchdog_task():
    """Restart provider discovery whenever it has gone quiet.

    Beat alone does not keep an importer running. Production stopped importing on
    2026-09-24 without a single error line: the ``imports`` lane was ~790 messages
    deep with ``auto_crawl_*`` retries, every discovery tick carried ``expires``
    shorter than its own schedule, and so each one aged out while it waited and
    the worker logged ``Discarding revoked task``. Beat kept firing, the worker
    kept looking busy, and no new title was imported for hours.

    That is one cause out of many with the same symptom — a worker killed while
    holding the 14-minute lock, a broker restart that drops the queued tick, a
    beat container that dies on its own. Rather than guard each cause separately,
    this checks the outcome: if a lane has not *finished* a run within its allowed
    silence, the lane is restarted, whatever stopped it — unless its lock is
    held, which means a run is in flight. A lock whose owner was killed is not
    cleared here: its TTL is shorter than the silence window, so it lapses on its
    own and the following tick restarts the lane.

    Runs on ``support``, which is the one lane that is never queued behind bulk
    work — a watchdog sharing a queue with what it watches cannot fire.
    """
    from django.conf import settings
    from django.core.cache import cache

    from config.celery import app as celery_app

    max_silent = float(getattr(settings, 'CATALOG_IMPORT_SILENCE_MINUTES', 45) or 45)
    restarted, healthy, running = [], [], []
    for lane, spec in DISCOVERY_LANES.items():
        if not getattr(settings, spec['enabled_setting'], True):
            continue
        silent_for = discovery_silent_minutes(lane)
        if silent_for is not None and silent_for < max_silent:
            healthy.append({'lane': lane, 'silent_minutes': round(silent_for, 1)})
            continue
        # A held lock means a run is in flight right now — typically a lane that
        # has never reported yet, whose first run is still going. Deleting it
        # used to start a second copy alongside (seen on the top250 lane's first
        # deploy). Every lock's TTL (14 min, 31 for top250) is shorter than the
        # silence window, so a lock orphaned by a killed worker expires on its own
        # and the next watchdog tick restarts the lane.
        if cache.get(spec['lock']):
            running.append(lane)
            continue
        celery_app.send_task(spec['task'], queue=spec.get('queue', 'imports-discovery'))
        logger.warning(
            'provider_import.discovery_restarted lane=%s silent_minutes=%s limit=%s',
            lane, 'never' if silent_for is None else round(silent_for, 1), max_silent,
        )
        restarted.append(lane)
    return {'restarted': restarted, 'healthy': healthy, 'running': running, 'silence_limit_minutes': max_silent}


@shared_task(name='apps.catalog.provider_import.tasks.reap_stale_import_jobs_task')
def reap_stale_import_jobs_task():
    """Release providers whose import job was abandoned by a dead worker.

    Without this, one recycled worker permanently wedges the admin importer for
    that provider — every later start answers 409 ``job_active``. See
    :func:`apps.catalog.provider_import.service.reap_stale_import_jobs`.
    """
    from .service import reap_stale_import_jobs

    result = reap_stale_import_jobs()
    if result.get('reaped'):
        logger.warning('provider_import.reap tick: %s', result)
    return result
