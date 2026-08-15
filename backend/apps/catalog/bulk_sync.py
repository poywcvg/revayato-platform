"""Persistent, cancellable TMDB catalog synchronization services."""

from __future__ import annotations

import time
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from .ingestion import load_media_manifest, upsert_tmdb_movie
from .imdb import configured_imdb_client
from .importer_config import get_importer_settings
from .models import CatalogSyncCandidate, CatalogSyncRun, Movie
from .tmdb import TMDBError, configured_tmdb_client


ACTIVE_STATUSES = (
    CatalogSyncRun.Status.QUEUED,
    CatalogSyncRun.Status.RUNNING,
    CatalogSyncRun.Status.CANCELLING,
)
TERMINAL_STATUSES = (
    CatalogSyncRun.Status.CANCELLED,
    CatalogSyncRun.Status.SUCCEEDED,
    CatalogSyncRun.Status.FAILED,
)


class ActiveCatalogSyncError(Exception):
    def __init__(self, run):
        super().__init__('A TMDB catalog sync is already active.')
        self.run = run


def catalog_sync_payload(run):
    total = int(run.total_count or 0)
    processed = int(run.processed_count or 0)
    progress = round((processed / total) * 100, 2) if total else 0
    requester = None
    if run.requested_by_id:
        requester = {
            'id': run.requested_by_id,
            'username': getattr(run.requested_by, 'username', ''),
        }
    return {
        'id': run.pk,
        'provider': run.provider,
        'mode': run.mode,
        'status': run.status,
        'phase': run.phase,
        'parameters': run.parameters,
        'started_at': run.started_at,
        'updated_at': run.updated_at,
        'heartbeat_at': run.heartbeat_at,
        'cancel_requested_at': run.cancel_requested_at,
        'finished_at': run.finished_at,
        'discovered_count': run.discovered_count,
        'total_count': total,
        'processed_count': processed,
        'created_count': run.created_count,
        'updated_count': run.updated_count,
        'published_count': run.published_count,
        'skipped_count': run.skipped_count,
        'error_count': run.error_count,
        'current_tmdb_id': run.current_tmdb_id,
        'progress_percent': progress,
        'is_active': run.status in ACTIVE_STATUSES,
        'can_cancel': run.status in {CatalogSyncRun.Status.QUEUED, CatalogSyncRun.Status.RUNNING},
        'errors': (run.errors or [])[-20:],
        'requested_by': requester,
    }


def start_catalog_sync(*, requested_by=None, mode=CatalogSyncRun.Mode.INCREMENTAL, parameters=None):
    if mode not in CatalogSyncRun.Mode.values:
        raise ValueError('Unsupported catalog sync mode.')
    with transaction.atomic():
        active = (
            CatalogSyncRun.objects.select_for_update()
            .filter(provider='tmdb', status__in=ACTIVE_STATUSES)
            .order_by('-started_at')
            .first()
        )
        if active:
            raise ActiveCatalogSyncError(active)
        try:
            return CatalogSyncRun.objects.create(
                provider='tmdb',
                mode=mode,
                status=CatalogSyncRun.Status.QUEUED,
                phase='queued',
                requested_by=requested_by,
                parameters=parameters or {},
            )
        except IntegrityError:
            active = CatalogSyncRun.objects.filter(
                provider='tmdb', status__in=ACTIVE_STATUSES,
            ).order_by('-started_at').first()
            raise ActiveCatalogSyncError(active) from None


def request_catalog_sync_cancel(run_id):
    with transaction.atomic():
        run = CatalogSyncRun.objects.select_for_update().get(pk=run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        now = timezone.now()
        if run.status == CatalogSyncRun.Status.QUEUED:
            run.status = CatalogSyncRun.Status.CANCELLED
            run.phase = 'cancelled'
            run.finished_at = now
        else:
            run.status = CatalogSyncRun.Status.CANCELLING
            run.phase = 'cancelling'
        run.cancel_requested_at = now
        run.heartbeat_at = now
        run.save(update_fields=[
            'status', 'phase', 'cancel_requested_at', 'heartbeat_at',
            'finished_at', 'updated_at',
        ])
        return run


def _cancel_if_requested(run_id):
    status = CatalogSyncRun.objects.filter(pk=run_id).values_list('status', flat=True).first()
    if status not in {CatalogSyncRun.Status.CANCELLING, CatalogSyncRun.Status.CANCELLED}:
        return False
    CatalogSyncRun.objects.filter(pk=run_id).exclude(
        status=CatalogSyncRun.Status.CANCELLED,
    ).update(
        status=CatalogSyncRun.Status.CANCELLED,
        phase='cancelled',
        finished_at=timezone.now(),
        heartbeat_at=timezone.now(),
        current_tmdb_id=None,
    )
    CatalogSyncCandidate.objects.filter(run_id=run_id).delete()
    return True


def _stage_candidates(run, summaries):
    batch_size = max(100, min(5000, int(getattr(settings, 'CATALOG_SYNC_STAGE_BATCH_SIZE', 2000))))
    buffer = []
    seen_count = 0
    for summary in summaries:
        if summary.get('adult', False) or summary.get('video', False) or not summary.get('id'):
            continue
        buffer.append(CatalogSyncCandidate(
            run=run,
            tmdb_id=int(summary['id']),
            popularity=float(summary.get('popularity') or 0),
        ))
        seen_count += 1
        if len(buffer) >= batch_size:
            CatalogSyncCandidate.objects.bulk_create(buffer, ignore_conflicts=True, batch_size=batch_size)
            buffer.clear()
            if _cancel_if_requested(run.pk):
                return False
            if seen_count % (batch_size * 5) == 0:
                count = CatalogSyncCandidate.objects.filter(run=run).count()
                CatalogSyncRun.objects.filter(pk=run.pk).update(
                    discovered_count=count,
                    heartbeat_at=timezone.now(),
                )
    if buffer:
        CatalogSyncCandidate.objects.bulk_create(buffer, ignore_conflicts=True, batch_size=batch_size)
    return not _cancel_if_requested(run.pk)


def stage_catalog_sync(run_id, *, client=None):
    client = client or configured_tmdb_client()
    importer = get_importer_settings()
    run = CatalogSyncRun.objects.get(pk=run_id)
    if run.status in TERMINAL_STATUSES or _cancel_if_requested(run.pk):
        return {'cancelled': True, 'ready': False}

    CatalogSyncRun.objects.filter(pk=run.pk).update(
        status=CatalogSyncRun.Status.RUNNING,
        phase='discovering',
        heartbeat_at=timezone.now(),
    )
    parameters = run.parameters or {}
    if run.mode == CatalogSyncRun.Mode.FULL:
        requested_export_date = parse_date(str(parameters.get('export_date') or ''))
        requested_export_date = requested_export_date or (date.today() - timedelta(days=1))
        staged = False
        last_error = None
        for days_back in range(3):
            export_date = requested_export_date - timedelta(days=days_back)
            try:
                if not _stage_candidates(run, client.iter_movie_export(export_date)):
                    return {'cancelled': True, 'ready': False}
                parameters['export_date'] = export_date.isoformat()
                staged = True
                break
            except TMDBError as exc:
                last_error = exc
                if exc.status_code != 404:
                    raise
        if not staged:
            raise last_error or TMDBError('No recent TMDB movie export is available.')
    elif run.mode == CatalogSyncRun.Mode.TRENDING:
        window = str(parameters.get('window') or importer.trending_window)
        window = window if window in {'day', 'week'} else 'day'
        max_pages = max(1, min(20, int(parameters.get(
            'max_pages', importer.trending_max_pages,
        ))))
        if not _stage_candidates(run, client.trending_movies(window=window, max_pages=max_pages)):
            return {'cancelled': True, 'ready': False}
        parameters.update({'window': window, 'max_pages': max_pages})
    else:
        lookback_days = max(1, min(14, int(parameters.get(
            'lookback_days', importer.daily_lookback_days,
        ))))
        lookahead_days = max(0, min(90, int(parameters.get(
            'lookahead_days', importer.daily_lookahead_days,
        ))))
        max_pages = max(1, min(500, int(parameters.get(
            'max_pages', importer.daily_max_pages,
        ))))
        today = date.today()
        changed = client.changed_movies(
            changed_from=today - timedelta(days=lookback_days),
            changed_until=today,
            max_pages=max_pages,
        )
        if not _stage_candidates(run, changed):
            return {'cancelled': True, 'ready': False}
        discovered = client.discover_movies(
            released_from=today - timedelta(days=lookback_days),
            released_until=today + timedelta(days=lookahead_days),
            max_pages=max_pages,
        )
        if not _stage_candidates(run, discovered):
            return {'cancelled': True, 'ready': False}
        if run.mode == CatalogSyncRun.Mode.DAILY:
            now_playing = client.now_playing_movies(max_pages=max_pages)
            if not _stage_candidates(run, now_playing):
                return {'cancelled': True, 'ready': False}
        if run.mode == CatalogSyncRun.Mode.DAILY:
            parameters.update({
                'lookback_days': lookback_days,
                'lookahead_days': lookahead_days,
                'max_pages': max_pages,
            })
            refresh_after_days = None
            stale_limit = 0
        else:
            refresh_after_days = max(30, min(179, int(getattr(
                settings, 'CATALOG_TMDB_REFRESH_AFTER_DAYS', 150,
            ))))
            stale_limit = max(0, min(100000, int(getattr(
                settings, 'CATALOG_SYNC_STALE_REFRESH_LIMIT', 50000,
            ))))
        if stale_limit:
            stale_before = timezone.now() - timedelta(days=refresh_after_days)
            stale_movies = Movie.objects.filter(tmdb_id__isnull=False).filter(
                Q(last_tmdb_sync_at__isnull=True) | Q(last_tmdb_sync_at__lt=stale_before),
            ).order_by('last_tmdb_sync_at', 'id').values('tmdb_id')[:stale_limit]
            stale_summaries = ({'id': item['tmdb_id']} for item in stale_movies)
            if not _stage_candidates(run, stale_summaries):
                return {'cancelled': True, 'ready': False}
        if run.mode == CatalogSyncRun.Mode.INCREMENTAL:
            parameters.update({
                'lookback_days': lookback_days,
                'lookahead_days': lookahead_days,
                'max_pages': max_pages,
                'refresh_after_days': refresh_after_days,
                'stale_refresh_limit': stale_limit,
            })

    total = CatalogSyncCandidate.objects.filter(run=run).count()
    now = timezone.now()
    updates = {
        'parameters': parameters,
        'discovered_count': total,
        'total_count': total,
        'phase': 'importing' if total else 'complete',
        'heartbeat_at': now,
    }
    if not total:
        updates.update(status=CatalogSyncRun.Status.SUCCEEDED, finished_at=now)
    CatalogSyncRun.objects.filter(pk=run.pk).update(**updates)
    return {'cancelled': False, 'ready': bool(total), 'total': total}


def _record_outcome(run_id, candidate, *, outcome, created=False, published=False, error=''):
    now = timezone.now()
    candidate.status = outcome
    candidate.error = (error or '')[:500]
    candidate.attempts += 1
    candidate.save(update_fields=['status', 'error', 'attempts', 'updated_at'])
    run_updates = {
        'processed_count': F('processed_count') + 1,
        'heartbeat_at': now,
        'current_tmdb_id': candidate.tmdb_id,
    }
    if outcome == CatalogSyncCandidate.Status.SUCCEEDED:
        run_updates['created_count' if created else 'updated_count'] = F(
            'created_count' if created else 'updated_count',
        ) + 1
        if published:
            run_updates['published_count'] = F('published_count') + 1
    elif outcome == CatalogSyncCandidate.Status.SKIPPED:
        run_updates['skipped_count'] = F('skipped_count') + 1
    else:
        run_updates['error_count'] = F('error_count') + 1
    CatalogSyncRun.objects.filter(pk=run_id).update(**run_updates)
    if error and outcome == CatalogSyncCandidate.Status.FAILED:
        with transaction.atomic():
            run = CatalogSyncRun.objects.select_for_update().get(pk=run_id)
            errors = list(run.errors or [])[-99:]
            errors.append({'tmdb_id': candidate.tmdb_id, 'error': error[:500]})
            run.errors = errors
            run.save(update_fields=['errors', 'updated_at'])


def process_catalog_sync_batch(run_id, *, client=None, manifest=None, batch_size=None):
    client = client or configured_tmdb_client()
    importer = get_importer_settings()
    imdb_client = configured_imdb_client() if importer.fetch_imdb_ratings else None
    manifest = manifest if manifest is not None else load_media_manifest(
        getattr(settings, 'CATALOG_MEDIA_MANIFEST', ''),
    )
    batch_size = max(1, min(100, int(
        batch_size or getattr(settings, 'CATALOG_SYNC_PROCESS_BATCH_SIZE', 20),
    )))
    max_attempts = max(1, min(10, int(getattr(settings, 'CATALOG_SYNC_ITEM_MAX_ATTEMPTS', 3))))
    items_per_second = max(0.2, min(15.0, float(
        getattr(settings, 'CATALOG_SYNC_ITEMS_PER_SECOND', 6),
    )))
    delay = 1 / items_per_second

    run = CatalogSyncRun.objects.get(pk=run_id)
    if run.status in TERMINAL_STATUSES or _cancel_if_requested(run.pk):
        return {'cancelled': True, 'has_more': False}
    candidates = list(CatalogSyncCandidate.objects.filter(
        run=run,
        status=CatalogSyncCandidate.Status.PENDING,
    ).order_by('id')[:batch_size])

    for candidate in candidates:
        if _cancel_if_requested(run.pk):
            return {'cancelled': True, 'has_more': False}
        started = time.monotonic()
        CatalogSyncRun.objects.filter(pk=run.pk).update(
            current_tmdb_id=candidate.tmdb_id,
            heartbeat_at=timezone.now(),
        )
        try:
            details = client.movie_details(candidate.tmdb_id)
            with transaction.atomic():
                movie, created, published, _skipped = upsert_tmdb_movie(
                    details,
                    media_entry=manifest.get(str(candidate.tmdb_id)),
                    auto_publish=bool(importer.auto_publish),
                    imdb_client=imdb_client,
                    importer=importer,
                )
                if run.mode == CatalogSyncRun.Mode.TRENDING and importer.feature_trending:
                    fields = []
                    if not movie.is_featured:
                        movie.is_featured = True
                        fields.append('is_featured')
                    if not movie.is_recommended:
                        movie.is_recommended = True
                        fields.append('is_recommended')
                    if fields:
                        movie.save(update_fields=[*fields, 'updated_at'])
                elif run.mode == CatalogSyncRun.Mode.DAILY:
                    if not movie.is_recommended:
                        movie.is_recommended = True
                        movie.save(update_fields=['is_recommended', 'updated_at'])
            _record_outcome(
                run.pk,
                candidate,
                outcome=CatalogSyncCandidate.Status.SUCCEEDED,
                created=created,
                published=published,
            )
        except TMDBError as exc:
            if exc.status_code == 404:
                _record_outcome(
                    run.pk,
                    candidate,
                    outcome=CatalogSyncCandidate.Status.SKIPPED,
                    error='TMDB item no longer exists.',
                )
            elif exc.retryable and candidate.attempts + 1 < max_attempts:
                CatalogSyncCandidate.objects.filter(pk=candidate.pk).update(
                    attempts=F('attempts') + 1,
                    error=str(exc)[:500],
                )
            else:
                _record_outcome(
                    run.pk,
                    candidate,
                    outcome=CatalogSyncCandidate.Status.FAILED,
                    error=str(exc),
                )
        except Exception as exc:  # isolate malformed titles and database validation failures
            _record_outcome(
                run.pk,
                candidate,
                outcome=CatalogSyncCandidate.Status.FAILED,
                error=f'{exc.__class__.__name__}: {str(exc)[:430]}',
            )
        remaining_delay = delay - (time.monotonic() - started)
        if remaining_delay > 0:
            time.sleep(remaining_delay)

    has_more = CatalogSyncCandidate.objects.filter(
        run=run,
        status=CatalogSyncCandidate.Status.PENDING,
    ).exists()
    if not has_more:
        CatalogSyncRun.objects.filter(pk=run.pk).update(
            status=CatalogSyncRun.Status.SUCCEEDED,
            phase='complete',
            finished_at=timezone.now(),
            heartbeat_at=timezone.now(),
            current_tmdb_id=None,
        )
        CatalogSyncCandidate.objects.filter(run=run).delete()
    return {'cancelled': False, 'has_more': has_more}


def fail_catalog_sync(run_id, error):
    with transaction.atomic():
        run = CatalogSyncRun.objects.select_for_update().get(pk=run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        errors = list(run.errors or [])[-99:]
        errors.append({'error': str(error)[:500]})
        run.errors = errors
        run.error_count = F('error_count') + 1
        run.status = CatalogSyncRun.Status.FAILED
        run.phase = 'failed'
        run.finished_at = timezone.now()
        run.heartbeat_at = timezone.now()
        run.current_tmdb_id = None
        run.save(update_fields=[
            'errors', 'error_count', 'status', 'phase', 'finished_at',
            'heartbeat_at', 'current_tmdb_id', 'updated_at',
        ])
        run.refresh_from_db()
        CatalogSyncCandidate.objects.filter(run_id=run_id).delete()
        return run
