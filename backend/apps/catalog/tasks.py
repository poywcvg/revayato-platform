from celery import shared_task
from datetime import timedelta
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db.models import Q
from django.utils import timezone

from .bulk_sync import (
    ActiveCatalogSyncError,
    fail_catalog_sync,
    process_catalog_sync_batch,
    stage_catalog_sync,
    start_catalog_sync,
)
from .models import CatalogSyncCandidate, CatalogSyncRun
from .importer_config import get_importer_settings


SOFTSUB_QUEUE_LOCK_TTL = 2 * 60 * 60


def _softsub_queue_lock(kind: str, object_id: int) -> str:
    return f'catalog:softsub:queued:{kind}:{int(object_id)}'


def enqueue_movie_softsub(movie_id: int, *, force: bool = False) -> bool:
    """Queue one movie at most once across beat/manual backfill runs."""
    key = _softsub_queue_lock('movie', movie_id)
    if not cache.add(key, 'queued', timeout=SOFTSUB_QUEUE_LOCK_TTL):
        return False
    try:
        extract_movie_softsub_task.delay(movie_id, force=force)
    except Exception:
        cache.delete(key)
        raise
    return True


def enqueue_movie_softsub_urgent(
    movie_id: int,
    *,
    force: bool = True,
    preferred_source_url: str = '',
) -> bool:
    """Bypass the long queue lock so an open player can refresh SoftSub immediately."""
    key = _softsub_queue_lock('movie', movie_id)
    cache.delete(key)
    if not cache.add(key, 'urgent', timeout=SOFTSUB_QUEUE_LOCK_TTL):
        return False
    try:
        extract_movie_softsub_task.apply_async(
            args=(int(movie_id),),
            kwargs={
                'force': bool(force),
                'preferred_source_url': str(preferred_source_url or '')[:2000],
            },
            queue='softsub-urgent',
            countdown=0,
        )
    except Exception:
        cache.delete(key)
        raise
    return True


def enqueue_series_softsub(
    series_id: int,
    *,
    force: bool = False,
    episode_limit: int = 24,
) -> bool:
    """Queue one bounded series batch at most once."""
    key = _softsub_queue_lock('series', series_id)
    if not cache.add(key, 'queued', timeout=SOFTSUB_QUEUE_LOCK_TTL):
        return False
    try:
        extract_series_softsub_task.delay(
            series_id,
            force=force,
            episode_limit=max(1, int(episode_limit)),
        )
    except Exception:
        cache.delete(key)
        raise
    return True


def enqueue_series_softsub_urgent(
    series_id: int,
    *,
    force: bool = True,
    episode_limit: int = 40,
    episode_id: int = 0,
    preferred_source_url: str = '',
) -> bool:
    """Bypass the long queue lock for an open series player SoftSub gap."""
    key = _softsub_queue_lock('series', series_id)
    cache.delete(key)
    if not cache.add(key, 'urgent', timeout=SOFTSUB_QUEUE_LOCK_TTL):
        return False
    try:
        extract_series_softsub_task.apply_async(
            args=(int(series_id),),
            kwargs={
                'force': bool(force),
                'episode_limit': max(1, int(episode_limit or 40)),
                'preferred_episode_id': max(0, int(episode_id or 0)),
                'preferred_source_url': str(preferred_source_url or '')[:2000],
            },
            queue='softsub-urgent',
            countdown=0,
        )
    except Exception:
        cache.delete(key)
        raise
    return True


def _remember_task(run_id, result):
    CatalogSyncRun.objects.filter(
        pk=run_id,
        status__in=[CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING],
    ).update(
        task_id=result.id,
        heartbeat_at=timezone.now(),
    )


@shared_task(
    bind=True,
    max_retries=3,
    soft_time_limit=55 * 60,
    time_limit=60 * 60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def stage_catalog_sync_task(self, run_id):
    try:
        result = stage_catalog_sync(run_id)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            CatalogSyncRun.objects.filter(pk=run_id).update(
                phase='discovery_retry',
                heartbeat_at=timezone.now(),
            )
            raise self.retry(exc=exc, countdown=min(60, 5 * (2 ** self.request.retries)))
        fail_catalog_sync(run_id, exc)
        return {'status': 'failed'}
    if result.get('ready'):
        try:
            next_task = process_catalog_sync_batch_task.apply_async(args=[run_id], countdown=1)
            _remember_task(run_id, next_task)
        except Exception:
            fail_catalog_sync(run_id, 'The next catalog import batch could not be queued.')
            return {'status': 'failed'}
    return result


@shared_task(bind=True, max_retries=2, acks_late=True, reject_on_worker_lost=True)
def process_catalog_sync_batch_task(self, run_id):
    try:
        result = process_catalog_sync_batch(run_id)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            CatalogSyncRun.objects.filter(pk=run_id).update(
                phase='import_retry',
                heartbeat_at=timezone.now(),
            )
            raise self.retry(exc=exc, countdown=min(60, 5 * (2 ** self.request.retries)))
        fail_catalog_sync(run_id, exc)
        return {'status': 'failed'}
    if result.get('has_more'):
        try:
            next_task = process_catalog_sync_batch_task.apply_async(args=[run_id], countdown=1)
            _remember_task(run_id, next_task)
        except Exception:
            fail_catalog_sync(run_id, 'The next catalog import batch could not be queued.')
            return {'status': 'failed'}
    return result


@shared_task
def catalog_sync_watchdog_task():
    """Recover stale jobs and finalize cancellation if a worker disappeared."""
    now = timezone.now()
    cancel_cutoff = now - timedelta(minutes=5)
    stale_cutoff = now - timedelta(minutes=max(
        5,
        int(getattr(settings, 'CATALOG_SYNC_STALE_HEARTBEAT_MINUTES', 15)),
    ))

    cancelling = CatalogSyncRun.objects.filter(
        status=CatalogSyncRun.Status.CANCELLING,
    ).filter(
        Q(heartbeat_at__lt=cancel_cutoff)
        | Q(heartbeat_at__isnull=True, started_at__lt=cancel_cutoff),
    )
    cancelled_ids = list(cancelling.values_list('id', flat=True))
    if cancelled_ids:
        cancelling.update(
            status=CatalogSyncRun.Status.CANCELLED,
            phase='cancelled',
            finished_at=now,
            heartbeat_at=now,
            current_tmdb_id=None,
        )
        CatalogSyncCandidate.objects.filter(run_id__in=cancelled_ids).delete()

    stale_runs = CatalogSyncRun.objects.filter(
        status__in=[CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING],
    ).filter(
        Q(heartbeat_at__lt=stale_cutoff)
        | Q(heartbeat_at__isnull=True, started_at__lt=stale_cutoff),
    ).order_by('started_at')
    recovered = []
    for run in stale_runs:
        if run.phase in {'importing', 'import_retry'}:
            task_function = process_catalog_sync_batch_task
            next_phase = 'import_retry'
        else:
            task_function = stage_catalog_sync_task
            next_phase = 'discovery_retry'
        claimed = CatalogSyncRun.objects.filter(
            pk=run.pk,
            status__in=[CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING],
        ).filter(
            Q(heartbeat_at__lt=stale_cutoff)
            | Q(heartbeat_at__isnull=True, started_at__lt=stale_cutoff),
        ).update(phase=next_phase, heartbeat_at=now)
        if not claimed:
            continue
        try:
            task = task_function.delay(run.pk)
            CatalogSyncRun.objects.filter(
                pk=run.pk,
                status__in=[CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING],
            ).update(
                task_id=task.id,
            )
            recovered.append(run.pk)
        except Exception:
            # Restore staleness so the next watchdog tick can retry the enqueue.
            CatalogSyncRun.objects.filter(
                pk=run.pk,
                status__in=[CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING],
            ).update(heartbeat_at=stale_cutoff - timedelta(minutes=1))
            continue
    return {'cancelled': cancelled_ids, 'recovered': recovered}


@shared_task(bind=True)
def sync_catalog_task(self):
    importer = get_importer_settings()
    if not importer.automation_enabled:
        return {'status': 'disabled'}
    last_scheduled = CatalogSyncRun.objects.filter(
        parameters__scheduled=True,
    ).order_by('-started_at').first()
    interval = timedelta(hours=max(1, int(importer.automation_interval_hours)))
    if last_scheduled and last_scheduled.started_at > timezone.now() - interval:
        return {'status': 'not_due', 'run_id': last_scheduled.pk}
    try:
        run = start_catalog_sync(
            mode=importer.automation_mode,
            parameters={
                'lookback_days': importer.daily_lookback_days,
                'lookahead_days': importer.daily_lookahead_days,
                'max_pages': (
                    importer.trending_max_pages
                    if importer.automation_mode == CatalogSyncRun.Mode.TRENDING
                    else importer.daily_max_pages
                ),
                'window': importer.trending_window,
                'scheduled': True,
            },
        )
    except ActiveCatalogSyncError as exc:
        return {'status': 'already_running', 'run_id': exc.run.pk}
    task = stage_catalog_sync_task.delay(run.pk)
    _remember_task(run.pk, task)
    return {'status': 'queued', 'run_id': run.pk}


@shared_task
def publish_ready_catalog_task():
    if not getattr(settings, 'CATALOG_AUTO_PUBLISH', False):
        return {'status': 'disabled'}
    call_command('publish_ready_catalog')


@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=22 * 60,
    time_limit=25 * 60,
    acks_late=True,
)
def extract_movie_softsub_task(
    self,
    movie_id: int,
    force: bool = False,
    preferred_source_url: str = '',
):
    """Extract SoftSub WebVTT for one published movie."""
    from apps.catalog.models import Movie
    from apps.catalog.subtitle_extract import attach_extracted_subtitle

    release_lock = True
    try:
        cache.set(
            _softsub_queue_lock('movie', movie_id),
            'active',
            timeout=SOFTSUB_QUEUE_LOCK_TTL,
        )
        movie = Movie.objects.filter(pk=movie_id, is_published=True).first()
        if movie is None:
            return {'movie_id': movie_id, 'status': 'missing'}
        # Online SoftSub: exact-container demux first, then provider fallbacks.
        from django.conf import settings as django_settings
        from apps.catalog.playback_subtitle import _clear_subtitlestar_miss_for_movie
        from apps.catalog.subtitle_extract import (
            download_links_imply_softsub,
            looks_like_hardsub_link,
            url_implies_softsub,
        )

        # Snappy ensure lookups must not leave a 24h miss that blocks this worker.
        _clear_subtitlestar_miss_for_movie(movie)

        links = [item for item in (movie.download_links or []) if isinstance(item, dict)]
        has_soft = (
            any(url_implies_softsub(item) for item in links)
            or download_links_imply_softsub(links)
        )
        soft_only = has_soft and not any(looks_like_hardsub_link(item) for item in links)
        allow_ffmpeg = (
            bool(getattr(django_settings, 'SOFTSUB_ALLOW_FFMPEG', False))
            or soft_only
            or has_soft
        )
        # Any trusted Soft encode wins over external providers: its timestamps are
        # native to the exact playback file and therefore frame-accurate.
        changed = attach_extracted_subtitle(
            movie,
            force=force,
            timeout_seconds=90 if not allow_ffmpeg else (110 if soft_only else 140),
            allow_ffmpeg=allow_ffmpeg,
            prefer_embedded=has_soft,
            preferred_source_url=preferred_source_url,
        )
        movie.refresh_from_db(fields=['subtitle_tracks'])
        if movie.subtitle_tracks:
            from apps.catalog.playback_subtitle import resolve_playback_subtitle_gaps

            first_track = movie.subtitle_tracks[0]
            provider = str(
                first_track.get('provider') if isinstance(first_track, dict) else 'ready'
            ) or 'ready'
            resolve_playback_subtitle_gaps(
                content_type='movie',
                object_id=movie.pk,
                last_result=provider,
            )
    except Exception as exc:
        if self.request.retries < self.max_retries:
            release_lock = False
            raise self.retry(exc=exc, countdown=60)
        raise
    finally:
        if release_lock:
            cache.delete(_softsub_queue_lock('movie', movie_id))
    return {'movie_id': movie_id, 'status': 'extracted' if changed else 'unchanged'}


@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=35 * 60,
    time_limit=40 * 60,
    acks_late=True,
)
def extract_series_softsub_task(
    self,
    series_id: int,
    force: bool = False,
    episode_limit: int = 60,
    preferred_episode_id: int = 0,
    preferred_source_url: str = '',
):
    """Extract SoftSub WebVTT for published episodes of one series."""
    from apps.catalog.models import Episode, Series
    from apps.catalog.subtitle_extract import (
        attach_series_softsub_tracks,
        download_links_imply_softsub,
        looks_like_hardsub_link,
        url_implies_softsub,
    )

    release_lock = True
    batch_limit = min(200, max(1, int(episode_limit or 60)))
    try:
        cache.set(
            _softsub_queue_lock('series', series_id),
            'active',
            timeout=SOFTSUB_QUEUE_LOCK_TTL,
        )
        series = Series.objects.filter(pk=series_id, is_published=True).first()
        if series is None:
            return {'series_id': series_id, 'status': 'missing'}

        from django.conf import settings as django_settings
        from apps.catalog.playback_subtitle import _clear_subtitlestar_miss_for_series

        _clear_subtitlestar_miss_for_series(series)

        links = [item for item in (series.download_links or []) if isinstance(item, dict)]
        has_soft = (
            any(url_implies_softsub(item) for item in links)
            or download_links_imply_softsub(links)
        )
        soft_only = has_soft and not any(looks_like_hardsub_link(item) for item in links)
        # Every Soft encode uses embedded extraction first; provider sites only
        # fill episodes whose own container did not yield a valid Persian track.
        allow_ffmpeg = (
            bool(getattr(django_settings, 'SOFTSUB_ALLOW_FFMPEG', False))
            or soft_only
            or has_soft
        )

        # Without Soft encodes we need SubtitleStar — defer while the circuit is open
        # instead of fanning out retries that re-trip 403s. Soft rows can still demux.
        if cache.get('catalog:subtitlestar:circuit-open') and not allow_ffmpeg:
            return {'series_id': series_id, 'status': 'deferred_circuit', 'soft_only': False}

        result = attach_series_softsub_tracks(
            series,
            force=force,
            timeout_seconds=150 if not allow_ffmpeg else (160 if soft_only else 180),
            limit=batch_limit,
            allow_ffmpeg=allow_ffmpeg,
            prefer_embedded=has_soft,
            preferred_episode_id=max(0, int(preferred_episode_id or 0)),
            preferred_source_url=preferred_source_url,
        )
        ready_episode_ids = list(
            Episode.objects.filter(
                season__series_id=series_id,
                is_published=True,
            )
            .exclude(subtitle_tracks=[])
            .exclude(subtitle_tracks__isnull=True)
            .values_list('pk', flat=True)
        )
        if ready_episode_ids:
            from apps.catalog.playback_subtitle import resolve_playback_subtitle_gaps

            resolve_playback_subtitle_gaps(
                content_type='series',
                object_id=series.pk,
                episode_ids=ready_episode_ids,
                last_result='ready',
            )
        result['soft_only'] = soft_only
        result['allow_ffmpeg'] = allow_ffmpeg
        result['has_soft'] = has_soft
        if (
            cache.get('catalog:subtitlestar:circuit-open')
            and int(result.get('extracted') or 0) == 0
            and not allow_ffmpeg
        ):
            return {'status': 'deferred_circuit', **result}

        still_missing = Episode.objects.filter(
            season__series_id=series_id,
            is_published=True,
        ).filter(Q(subtitle_tracks__isnull=True) | Q(subtitle_tracks=[])).exclude(
            video_url='',
        ).exclude(video_url__isnull=True).exists()
        if still_missing and int(result.get('extracted') or 0) > 0:
            cache.delete(_softsub_queue_lock('series', series_id))
            release_lock = False
            extract_series_softsub_task.apply_async(
                args=[series_id],
                # Continue from still-missing episodes; forcing again would keep
                # re-demuxing the same first batch and starve later episodes.
                kwargs={'force': False, 'episode_limit': batch_limit},
                countdown=30,
            )
            cache.set(_softsub_queue_lock('series', series_id), 'queued', timeout=SOFTSUB_QUEUE_LOCK_TTL)
            result['requeued'] = True
    except Exception as exc:
        if self.request.retries < self.max_retries:
            release_lock = False
            raise self.retry(exc=exc, countdown=90)
        raise
    finally:
        if release_lock:
            cache.delete(_softsub_queue_lock('series', series_id))
    return {'status': 'ok', **result}



@shared_task(soft_time_limit=25 * 60, time_limit=30 * 60)
def backfill_softsub_tracks_task():
    """Periodic catch-up for SoftSub WebVTT extraction across the catalog."""
    # Prefer Soft-only titles still missing WebVTT; keep batches small so the
    # softsub-urgent queue stays responsive for open players.
    call_command(
        'extract_softsub_tracks',
        limit=24,
        movie_limit=18,
        series_limit=10,
        timeout=180,
        episode_limit=16,
        missing_only=True,
        soft_only=True,
        queue=True,
    )
    return {'status': 'ok'}


# Ensure Celery workers load provider-import tasks via this module.
from apps.catalog.provider_import.tasks import run_provider_import_job_task  # noqa: E402,F401
