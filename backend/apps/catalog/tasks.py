import logging

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


logger = logging.getLogger(__name__)


SOFTSUB_QUEUE_LOCK_TTL = 2 * 60 * 60

# Back-pressure. The per-title lock below bounds duplicates *per two hours*, not
# *per queue*: once the consumer is slower than the producer, every lock expires
# long before its task is ever popped and the same title is queued again, which
# makes the queue deeper, which makes the next lock expire even further ahead of
# consumption. Measured on production 2026-09-24, that loop had run the softsub
# lane to 154,475 tasks for a 23,477-title catalog — 6.6 copies of the whole
# archive, and 1.8 years of work at the observed ~10 tasks/hour.
#
# A depth ceiling breaks the loop no matter how slow the consumer gets: above the
# mark nothing new is admitted, so the queue is bounded by construction and the
# worker always drains toward it. Skipped titles are not lost — the beat backfill
# re-offers them once the lane has room.
SOFTSUB_QUEUE_NAME = 'softsub'
SOFTSUB_QUEUE_DEPTH_CACHE_KEY = 'catalog:softsub:depth'
SOFTSUB_QUEUE_DEPTH_CACHE_TTL = 30


def _softsub_queue_lock(kind: str, object_id: int) -> str:
    return f'catalog:softsub:queued:{kind}:{int(object_id)}'


def softsub_queue_depth(*, use_cache: bool = True) -> int:
    """Current broker depth of the softsub lane, or -1 when it cannot be read.

    Cached briefly because this runs in front of every enqueue; an LLEN per
    candidate would make the backfill loop itself a load source.
    """
    if use_cache:
        cached = cache.get(SOFTSUB_QUEUE_DEPTH_CACHE_KEY)
        if cached is not None:
            return int(cached)
    try:
        from config.celery import app as celery_app

        with celery_app.connection_or_acquire() as conn:
            depth = int(conn.default_channel.client.llen(SOFTSUB_QUEUE_NAME))
    except Exception:
        # Never let a broker-introspection failure block real work: an unknown
        # depth admits the task, exactly as before this gate existed.
        return -1
    if use_cache:
        cache.set(SOFTSUB_QUEUE_DEPTH_CACHE_KEY, depth, timeout=SOFTSUB_QUEUE_DEPTH_CACHE_TTL)
    return depth


def softsub_queue_saturated() -> bool:
    """True when the softsub lane is too deep to accept more background work."""
    limit = int(getattr(settings, 'CATALOG_SOFTSUB_QUEUE_MAX_DEPTH', 5000) or 0)
    if limit <= 0:
        return False
    depth = softsub_queue_depth()
    if depth < 0:
        return False
    if depth >= limit:
        logger.info('catalog.softsub_queue_saturated depth=%s limit=%s', depth, limit)
        return True
    return False


def enqueue_movie_softsub(movie_id: int, *, force: bool = False) -> bool:
    """Queue one movie at most once across beat/manual backfill runs."""
    if softsub_queue_saturated():
        return False
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
    if softsub_queue_saturated():
        return False
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
    # Bounded: every candidate costs a live probe of its sources, and this runs
    # every few minutes — an unbounded pass over the draft backlog would hold the
    # worker for the whole interval.
    call_command('publish_ready_catalog', limit=getattr(settings, 'CATALOG_PUBLISH_BATCH_SIZE', 50))


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
        # Background lane: this worker owns a 22-minute budget, so embedded demux
        # of the film's own container gets minutes per source (snappy=False)
        # instead of the urgent 70s ceiling that timed out on slow remote MKVs.
        changed = attach_extracted_subtitle(
            movie,
            force=force,
            timeout_seconds=90 if not allow_ffmpeg else (480 if soft_only else 360),
            allow_ffmpeg=allow_ffmpeg,
            prefer_embedded=has_soft,
            snappy=False,
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
        else:
            from apps.catalog.playback_subtitle import mark_playback_subtitle_gaps_exhausted

            # The whole pipeline (own container, SubtitleStar, Subzone) ran and
            # came back empty: stop viewers re-queueing and polling it.
            mark_playback_subtitle_gaps_exhausted(content_type='movie', object_id=movie.pk)
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

        # Background lane (35-minute budget): give each episode's own container a
        # real per-source demux budget (snappy=False). Kept moderate because the
        # budget is spent per episode across the batch — the worker's soft time
        # limit still bounds a large fresh batch, and SubtitleStar season ZIPs
        # usually cover many episodes at once regardless.
        result = attach_series_softsub_tracks(
            series,
            force=force,
            timeout_seconds=150 if not allow_ffmpeg else (180 if soft_only else 160),
            limit=batch_limit,
            allow_ffmpeg=allow_ffmpeg,
            prefer_embedded=has_soft,
            snappy=False,
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
        elif int(result.get('extracted') or 0) == 0:
            # A pass that found nothing: the episode the viewer is on (or the
            # series-level report when none was given) is exhausted for now.
            from apps.catalog.playback_subtitle import mark_playback_subtitle_gaps_exhausted

            target_episode = max(0, int(preferred_episode_id or 0))
            if target_episode not in ready_episode_ids and (target_episode or not ready_episode_ids):
                result['exhausted'] = mark_playback_subtitle_gaps_exhausted(
                    content_type='series',
                    object_id=series.pk,
                    episode_ids=[target_episode],
                )
    except Exception as exc:
        if self.request.retries < self.max_retries:
            release_lock = False
            raise self.retry(exc=exc, countdown=90)
        raise
    finally:
        if release_lock:
            cache.delete(_softsub_queue_lock('series', series_id))
    return {'status': 'ok', **result}



REFRESH_EXPIRED_LOCK_TTL = 60 * 60


@shared_task(soft_time_limit=55 * 60, time_limit=60 * 60)
def refresh_expired_playback_task():
    """Periodically re-crawl published titles whose download/playback links have
    expired (Dornatv CDN signatures self-expire ~13 h) so the online player never
    goes dark. Bounded, lock-guarded, and low-priority like the catalog crawler."""
    from django.conf import settings as django_settings
    from django.core.cache import cache

    from apps.catalog.playback_refresh import refresh_broken_playback

    lock_key = 'catalog:refresh-expired-playback:lock'
    if not cache.add(lock_key, 'running', timeout=REFRESH_EXPIRED_LOCK_TTL):
        return {'status': 'already_running'}
    try:
        return refresh_broken_playback(
            max_batch=int(getattr(django_settings, 'PLAYBACK_REFRESH_BATCH_SIZE', 120)),
            delete=bool(getattr(django_settings, 'PLAYBACK_REFRESH_DELETE', False)),
            delay=float(getattr(django_settings, 'PLAYBACK_REFRESH_DELAY_SECONDS', 0.3)),
        )
    finally:
        cache.delete(lock_key)


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


def drain_playback_subtitle_gaps(
    *,
    max_batch: int = 20,
    min_age_seconds: int = 600,
    max_attempts: int = 3,
    reset_drain_count: bool = False,
    dry_run: bool = False,
) -> dict:
    """Re-enqueue stale OPEN/QUEUED playback gaps so a dead worker cannot orphan
    a viewer report forever. Pure enqueue + track-check: no provider work, no
    circuit/miss cache clearing (a fresh probe is the worker's job).

    Returns counts so both the beat task and the management command can report.
    ``dry_run=True`` never enqueues, never claims locks, never mutates rows —
    it only tallies what a real pass would do.
    """
    from datetime import timedelta

    from django.utils import timezone as dj_timezone

    from .models import PlaybackSubtitleGap

    gap_drain_lock_ttl = 10 * 60
    stale_before = dj_timezone.now() - timedelta(seconds=max(60, int(min_age_seconds)))
    # UNAVAILABLE rows (transient broker failure / queue down at report time)
    # get a longer cool-down but are never orphaned forever.
    unavailable_before = dj_timezone.now() - timedelta(seconds=max(1800, int(min_age_seconds) * 3))
    rows = list(
        PlaybackSubtitleGap.objects.filter(
            status__in=[PlaybackSubtitleGap.Status.OPEN, PlaybackSubtitleGap.Status.QUEUED],
            updated_at__lt=stale_before,
        ).order_by('updated_at')[:max(1, int(max_batch))]
    )
    remaining = max(1, int(max_batch)) - len(rows)
    if remaining > 0:
        # Exhausted rows are not transient failures: a full pass found nothing,
        # so only a viewer opening the title after the cooldown retries them.
        rows.extend(
            PlaybackSubtitleGap.objects.filter(
                status=PlaybackSubtitleGap.Status.UNAVAILABLE,
                updated_at__lt=unavailable_before,
            ).exclude(last_result__in=_GAP_FINAL_RESULTS).order_by('updated_at')[:remaining]
        )

    stats = {
        'processed': 0, 'enqueued': 0, 're_enqueued': 0, 'resolved': 0, 'skipped': 0,
        'exhausted': 0, 'closed': 0,
    }
    for gap in rows:
        stats['processed'] += 1
        # Per-row claim so concurrent beats/commands never double-enqueue.
        lock_key = f'catalog:gap-drain:{gap.pk}'
        if dry_run:
            attempts = 0 if reset_drain_count else int((gap.meta or {}).get('drain_count') or 0)
            if _gap_has_tracks(gap):
                stats['resolved'] += 1
            elif _gap_close_reason(gap):
                stats['closed'] += 1
            elif attempts >= 1 and _gap_burned_in_only(gap):
                stats['exhausted'] += 1
            elif attempts < max(1, int(max_attempts)):
                stats['re_enqueued'] += 1
            else:
                stats['exhausted'] += 1
            continue
        if not cache.add(lock_key, 'draining', timeout=gap_drain_lock_ttl):
            stats['skipped'] += 1
            continue

        attempts = int((gap.meta or {}).get('drain_count') or 0)
        if reset_drain_count:
            attempts = 0
        try:
            # If tracks landed since the report, just close it.
            if _gap_has_tracks(gap):
                from .playback_subtitle import resolve_playback_subtitle_gaps

                resolve_playback_subtitle_gaps(
                    content_type=gap.content_type,
                    object_id=gap.object_id,
                    episode_ids=[gap.episode_id] if gap.episode_id else None,
                    last_result='ready',
                )
                stats['resolved'] += 1
                continue

            closed_as = _gap_close_reason(gap)
            if closed_as:
                # Title gone, or a dub / Persian-language title: no crawler can
                # help, so stop spending urgent-lane passes on it every tick.
                gap.status = PlaybackSubtitleGap.Status.UNAVAILABLE
                gap.last_result = closed_as
                gap.save(update_fields=['status', 'last_result', 'updated_at'])
                stats['closed'] += 1
                continue

            if attempts >= 1 and _gap_burned_in_only(gap):
                # The worker already probed these files once and every one is
                # Dubbed/HardSub by name: no sidecar can bind, so answer viewers
                # at once for a week (a new encode's source_path reopens it).
                from .playback_subtitle import BURNED_IN_ONLY, mark_playback_subtitle_gaps_exhausted

                mark_playback_subtitle_gaps_exhausted(
                    content_type=gap.content_type,
                    object_id=gap.object_id,
                    episode_ids=[int(gap.episode_id or 0)],
                    reason=BURNED_IN_ONLY,
                )
                stats['exhausted'] += 1
                continue

            if attempts >= max(1, int(max_attempts)):
                # Every retry came back empty. Record the verdict instead of
                # touching the row forever: capped rows used to stay OPEN/QUEUED,
                # win a batch slot every tick and starve fresh viewer reports.
                # The next viewer after the exhausted cooldown retries it.
                from .playback_subtitle import mark_playback_subtitle_gaps_exhausted

                mark_playback_subtitle_gaps_exhausted(
                    content_type=gap.content_type,
                    object_id=gap.object_id,
                    episode_ids=[int(gap.episode_id or 0)],
                )
                stats['exhausted'] += 1
                continue

            meta = dict(gap.meta or {})
            preferred_source_url = str(meta.get('preferred_source_url') or '')
            if gap.content_type == PlaybackSubtitleGap.ContentType.MOVIE:
                queued = enqueue_movie_softsub_urgent(
                    gap.object_id,
                    force=True,
                    preferred_source_url=preferred_source_url,
                )
            else:
                ep_id = int(gap.episode_id or 0)
                queued = enqueue_series_softsub_urgent(
                    gap.object_id,
                    force=True,
                    episode_limit=8 if ep_id else 24,
                    episode_id=ep_id,
                    preferred_source_url=preferred_source_url,
                )
            if queued:
                # Worker holds the 2h queue lock now; next beat may resolve us.
                _touch_gap_meta(gap, {'drain_count': attempts + 1})
                gap.status = PlaybackSubtitleGap.Status.QUEUED
                gap.last_result = 'drain_re_enqueued'
                gap.save(update_fields=['status', 'last_result', 'meta', 'updated_at'])
                stats['re_enqueued'] += 1
            else:
                # 2h queue lock held by an in-flight worker — don't stampede it.
                stats['skipped'] += 1
        finally:
            cache.delete(lock_key)
    return stats


# Verdicts the drain never revisits; only a new viewer report reopens them.
_GAP_FINAL_RESULTS = ('exhausted', 'not_needed', 'dubbed_stream', 'persian_original', 'object_missing')


def _gap_close_reason(gap) -> str:
    """Why a gap can never be filled by a crawler, or ``''`` when it can."""
    from .models import Movie, PlaybackSubtitleGap, Series
    from .playback_subtitle import playback_subtitle_not_needed

    model = Movie if gap.content_type == PlaybackSubtitleGap.ContentType.MOVIE else Series
    obj = model.objects.filter(pk=gap.object_id, is_published=True).only('original_language').first()
    if obj is None:
        return 'object_missing'
    return playback_subtitle_not_needed(
        obj,
        version=gap.playback_version,
        preferred_source_url=str((gap.meta or {}).get('preferred_source_url') or ''),
    )


def _gap_burned_in_only(gap) -> bool:
    from .models import Movie, PlaybackSubtitleGap, Series
    from .playback_subtitle import title_is_burned_in_only

    model = Movie if gap.content_type == PlaybackSubtitleGap.ContentType.MOVIE else Series
    obj = model.objects.filter(pk=gap.object_id).only('download_links').first()
    return bool(obj is not None and title_is_burned_in_only(obj))


def _gap_has_tracks(gap) -> bool:
    # ``PlaybackSubtitleGap`` must be imported here too: without it every drain
    # tick raised NameError, so the safety net never re-enqueued a single gap.
    from .models import Episode, Movie, PlaybackSubtitleGap, Series
    from .playback_subtitle import _has_tracks

    if gap.content_type == PlaybackSubtitleGap.ContentType.MOVIE:
        movie = Movie.objects.filter(pk=gap.object_id, is_published=True).only(
            'subtitle_tracks', 'has_subtitle',
        ).first()
        return bool(movie and _has_tracks(movie.subtitle_tracks))
    # Series carries no ``subtitle_tracks`` column — cues live on its episodes.
    if not Series.objects.filter(pk=gap.object_id, is_published=True).exists():
        return False
    qs = Episode.objects.filter(season__series_id=gap.object_id, is_published=True)
    if gap.episode_id:
        qs = qs.filter(pk=gap.episode_id)
    return qs.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()


def _touch_gap_meta(gap, updates: dict) -> None:
    merged = dict(gap.meta or {})
    merged.update(updates)
    gap.meta = merged
    gap.save(update_fields=['meta', 'updated_at'])


@shared_task
def drain_playback_subtitle_gaps_task():
    """Periodic safety net: re-enqueue viewer reports a dead worker may have
    dropped so open players still get cues (see drain_playback_subtitle_gaps)."""
    from django.conf import settings as django_settings

    return drain_playback_subtitle_gaps(
        max_batch=int(getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MAX_PER_BATCH', 20)),
        min_age_seconds=int(getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MIN_AGE_SECONDS', 600)),
        max_attempts=int(getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MAX_ATTEMPTS', 3)),
    )


@shared_task(soft_time_limit=8 * 60, time_limit=10 * 60)
def verify_subtitle_sync_task():
    """Bake crowd-sourced subtitle timing consensus into served VTT files.

    The workhorse of the auto-sync system: promotes settled viewer offsets into
    the stored files (crowd consensus per exact file version), then prunes stale
    votes. Bounded per tick so it never contends with playback or the crawlers.
    """
    from django.conf import settings as django_settings
    from apps.catalog.subtitle_sync import promote_pending_offsets, prune_stale_votes

    promoted = promote_pending_offsets(
        max_groups=int(getattr(django_settings, 'SUBTITLE_SYNC_MAX_GROUPS_PER_TICK', 200)),
    )
    pruned = prune_stale_votes(
        max_age_days=int(getattr(django_settings, 'SUBTITLE_SYNC_VOTE_MAX_AGE_DAYS', 30)),
    )
    return {'promoted': promoted, 'pruned': pruned}


# Ensure Celery workers load provider-import tasks via this module.
from apps.catalog.provider_import.tasks import run_provider_import_job_task  # noqa: E402,F401


# --- viewer content-issue reports («گزارش خطا») ------------------------------
# Both tasks run on the dedicated ``support`` queue so a viewer's report is worked
# within seconds instead of queueing behind the long playback-refresh crawl.

@shared_task(
    name='apps.catalog.tasks.handle_content_report_task',
    time_limit=420, soft_time_limit=400,
)
def handle_content_report_task(report_id: int):
    """Fix one freshly-filed report, then let its support ticket tell the viewer.

    Order matters: remediate first so the ticket's reply states the real outcome
    (fixed / working on it / no safe source yet) rather than a placeholder.
    """
    from apps.catalog.content_remediation import remediate_report
    from apps.catalog.models import ContentIssueReport

    report = ContentIssueReport.objects.filter(pk=report_id).first()
    if report is None:
        return {'report_id': report_id, 'status': 'missing'}
    outcome = remediate_report(report)
    if report.support_ticket_id:
        from apps.engagement.support_automation import process_ticket

        process_ticket(report.support_ticket_id)
    return {k: outcome.get(k) for k in ('report_id', 'status', 'action', 'result')}


@shared_task(
    name='apps.catalog.tasks.drain_content_reports_task',
    time_limit=900, soft_time_limit=840,
)
def drain_content_reports_task(limit: int = 5):
    """Periodic safety net + long-tail worker for content-issue reports.

    1. crawl-free sweep — resolve every playback report whose target now plays
       (a crawler landed a mirror), so no viewer waits on a stale row;
    2. re-crawl a small batch of *due* reports on a widening backoff;
    3. tell the owners of every report resolved this tick.
    """
    from apps.catalog.content_remediation import remediate_open_reports, sync_reports_with_reality

    sync = sync_reports_with_reality()
    drained = remediate_open_reports(limit=limit)

    resolved_ids = set(sync['resolved_report_ids'])
    resolved_ids.update(
        o['report_id'] for o in drained['outcomes'] if o.get('status') == 'resolved'
    )
    notified = 0
    if resolved_ids:
        from apps.engagement.support_automation import close_tickets_for_reports

        notified = close_tickets_for_reports(resolved_ids)

    return {
        'synced_checked': sync['checked'],
        'synced_resolved': sync['resolved'],
        'processed': drained['processed'],
        'resolved': drained['resolved'],
        'exhausted': drained['exhausted'],
        'tickets_closed': notified,
    }


@shared_task(
    name='apps.catalog.tasks.verify_catalog_media_task',
    time_limit=900, soft_time_limit=840,
)
def verify_catalog_media_task(limit: int = 0):
    """Keep published titles honest after they go live.

    The publish gate proves a title worked *at publish time*. Signed provider
    URLs expire in about thirteen hours and mirrors get purged without notice,
    so a verified title decays into a broken one on its own. This sweep re-tests
    the titles whose verdict has gone stale and routes what it finds:

    * sources gone, links remain → hand it to the provider re-crawl, the same
      repair path a viewer report would trigger — except no viewer had to file it;
    * nothing left to serve at all → send it back to draft rather than leave a
      dead page published (capped per run, so a CDN outage cannot empty the site).
    """
    from apps.catalog.media_verification import sweep_published_media

    return sweep_published_media(limit=limit or None)


@shared_task(
    soft_time_limit=20 * 60,
    time_limit=25 * 60,
    autoretry_for=(OSError,),
    retry_backoff=300,
    retry_kwargs={'max_retries': 3},
)
def sync_imdb_ratings_task(limit: int = 0, only_missing: bool = False):
    """Keep every rating equal to IMDb's own, forever.

    IMDb republishes its ratings file daily and scores move as votes come in, so
    an accurate catalog is not a one-off backfill — it is this task. It reads
    the file once and bulk-updates only the rows whose number actually changed,
    which on a settled catalog is a few hundred rather than twenty thousand.
    """
    from . import imdb_dataset

    result = imdb_dataset.sync_catalog_ratings(limit=limit, only_missing=only_missing)
    logger.info(
        'catalog.imdb_ratings_synced checked=%s updated=%s filled=%s corrected=%s unrated=%s',
        result['checked'], result['updated'], result['filled'],
        result['corrected'], result['unrated_by_imdb'],
    )
    return result


@shared_task(
    soft_time_limit=25 * 60,
    time_limit=30 * 60,
)
def hunt_draft_sources_task(scan_limit: int = 0, fix_limit: int = 12, delay: float = 1.5):
    """Keep filling the archive: give sourceless drafts real download links.

    Most unpublished titles came from the metadata crawlers and were never
    matched to a provider page, so nothing ever looked at them again. This runs
    the enrolment scan (cheap, database only) and then spends a small provider
    budget hunting sources for the front of the queue. ``delay`` defaults to
    1.5s because the provider rate limit is shared with the live catalog crawler
    — this job must never starve it.
    """
    from . import draft_sources

    scanned = draft_sources.scan(limit=scan_limit)
    hunted = draft_sources.hunt_open_gaps(limit=fix_limit, delay=delay)
    logger.info(
        'catalog.draft_sources sourceless=%s enrolled=%s sourced=%s unplayable=%s '
        'unavailable=%s published=%s',
        scanned['scanned'], scanned['recorded'], hunted['sourced'], hunted['unplayable'],
        hunted['unavailable'], hunted['published'],
    )
    return {'scan': scanned, 'hunt': hunted}


@shared_task(soft_time_limit=5 * 60, time_limit=6 * 60)
def fill_link_sizes_task(limit: int = 0):
    """Give every download link its measured file size. See apps.catalog.link_sizes."""
    from django.conf import settings

    from apps.catalog.link_sizes import fill_missing_sizes

    return fill_missing_sizes(
        limit=limit or settings.CATALOG_LINK_SIZE_TITLES_PER_TICK,
        budget_seconds=settings.CATALOG_LINK_SIZE_BUDGET_SECONDS,
    )
