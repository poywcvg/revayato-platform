"""Provider import job orchestration."""

from __future__ import annotations

from django.utils import timezone

from apps.catalog.models import (
    ProviderCredential,
    ProviderImportItem,
    ProviderImportJob,
    ProviderImportLog,
    ProviderSource,
)

from .base import sanitize_payload
from .exceptions import (
    JobCancelled,
    ProviderCaptchaRequired,
    ProviderContractUnknown,
    ProviderImportError,
    ProviderNotConfigured,
)
from .matcher import match_movie, match_series, movie_has_available_archive
from .registry import get_connector


def ensure_avasarami_provider() -> ProviderSource:
    from django.conf import settings

    provider, _ = ProviderSource.objects.update_or_create(
        slug='avasarami',
        defaults={
            'name': 'Avasarami',
            'provider_type': ProviderSource.ProviderType.CUSTOM,
            'base_url': getattr(settings, 'AVASARAMI_BASE_URL', 'https://avasarami.top'),
            'auth_type': (
                getattr(settings, 'AVASARAMI_AUTH_TYPE', '')
                or ProviderSource.AuthType.NONE
            ),
            'is_active': True,
            'rate_limit_per_minute': getattr(settings, 'AVASARAMI_RATE_LIMIT_PER_MINUTE', 30),
            'timeout_seconds': getattr(settings, 'AVASARAMI_TIMEOUT_SECONDS', 30),
            'verify_ssl': getattr(settings, 'AVASARAMI_VERIFY_SSL', True),
            'config': {
                'login_url': getattr(settings, 'AVASARAMI_LOGIN_URL', ''),
                'movies_url': getattr(settings, 'AVASARAMI_MOVIES_URL', ''),
                'series_url': getattr(settings, 'AVASARAMI_SERIES_URL', ''),
                'supports_movies': True,
                'supports_series': True,
            },
        },
    )
    ProviderCredential.objects.get_or_create(
        provider=provider,
        defaults={
            'secret_mode': ProviderCredential.SecretMode.ENV,
            'env_prefix': 'AVASARAMI',
            'status': ProviderCredential.Status.UNKNOWN,
        },
    )
    return provider


def append_log(job, level, message, context=None):
    from .sanitizers import sanitize_payload as _sanitize

    ProviderImportLog.objects.create(
        job=job,
        level=level,
        message=str(_sanitize(message))[:500],
        context=_sanitize(context or {}),
    )


def refresh_job(job_id) -> ProviderImportJob:
    return ProviderImportJob.objects.select_related('provider').get(pk=job_id)


def job_cancelled(job: ProviderImportJob) -> bool:
    if job.cancel_requested or job.status == ProviderImportJob.Status.CANCEL_REQUESTED:
        return True
    fresh = ProviderImportJob.objects.filter(pk=job.pk).values(
        'cancel_requested', 'status',
    ).first()
    if not fresh:
        return True
    return bool(
        fresh['cancel_requested']
        or fresh['status'] == ProviderImportJob.Status.CANCEL_REQUESTED
    )


def secret_flags_for_provider(provider: ProviderSource) -> dict:
    from .sanitizers import secret_flags_from_settings

    prefix = 'AVASARAMI'
    cred = getattr(provider, 'credential', None)
    if cred and cred.env_prefix:
        prefix = cred.env_prefix
    elif provider.slug == 'myf2m':
        prefix = 'MYF2M'
    elif provider.slug == 'dornatv':
        prefix = 'DORNATV'
    return secret_flags_from_settings(prefix=prefix)


def create_import_job(*, provider, user, content_type, mode, params) -> ProviderImportJob:
    return ProviderImportJob.objects.create(
        provider=provider,
        started_by=user,
        content_type=content_type,
        mode=mode,
        params=sanitize_payload(params or {}),
        status=ProviderImportJob.Status.QUEUED,
    )


def run_provider_import_job(job_id) -> dict:
    job = refresh_job(job_id)
    if job.status in {
        ProviderImportJob.Status.COMPLETED,
        ProviderImportJob.Status.FAILED,
        ProviderImportJob.Status.CANCELLED,
    }:
        return {'status': job.status}

    job.status = ProviderImportJob.Status.RUNNING
    job.started_at = job.started_at or timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
    append_log(job, 'info', f'Job started ({job.mode} / {job.content_type}).')

    try:
        connector = get_connector(job.provider)
        auth = connector.authenticate()
        cred, _ = ProviderCredential.objects.get_or_create(provider=job.provider)
        cred.status = ProviderCredential.Status.VALID
        cred.last_validated_at = timezone.now()
        cred.last_validation_message = auth.message[:500]
        cred.save(update_fields=[
            'status', 'last_validated_at', 'last_validation_message', 'updated_at',
        ])
        append_log(job, 'info', auth.message, {'auth_type': auth.auth_type})

        discovered = _discover_items(job, connector)
        if job_cancelled(job):
            return _mark_cancelled(job)

        for item in discovered:
            if job_cancelled(job):
                return _mark_cancelled(job)
            _process_item(job, connector, item)

        job.status = ProviderImportJob.Status.COMPLETED
        job.finished_at = timezone.now()
        job.current_item_label = ''
        job.save(update_fields=[
            'status', 'finished_at', 'current_item_label', 'updated_at',
            'processed_items', 'matched_items', 'imported_files',
            'skipped_items', 'failed_items', 'total_items',
        ])
        append_log(job, 'info', 'Job completed.')
        return {'status': job.status}
    except ProviderCaptchaRequired as exc:
        return _fail_job(job, str(exc), credential_status=ProviderCredential.Status.NEEDS_INTERACTIVE)
    except (ProviderNotConfigured, ProviderContractUnknown, ProviderImportError) as exc:
        return _fail_job(job, str(exc))
    except Exception as exc:
        append_log(job, 'error', f'Unexpected failure: {exc}')
        return _fail_job(job, 'Provider import failed unexpectedly.')


def _fail_job(job, message, credential_status=ProviderCredential.Status.INVALID):
    job.status = ProviderImportJob.Status.FAILED
    job.error_message = str(message)[:500]
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
    append_log(job, 'error', job.error_message)
    try:
        cred = job.provider.credential
        cred.status = credential_status
        cred.last_validated_at = timezone.now()
        cred.last_validation_message = job.error_message
        cred.save(update_fields=[
            'status', 'last_validated_at', 'last_validation_message', 'updated_at',
        ])
    except ProviderCredential.DoesNotExist:
        pass
    return {'status': job.status, 'error': job.error_message}


def _mark_cancelled(job):
    job.status = ProviderImportJob.Status.CANCELLED
    job.finished_at = timezone.now()
    job.current_item_label = ''
    job.save(update_fields=['status', 'finished_at', 'current_item_label', 'updated_at'])
    append_log(job, 'warning', 'Job cancelled.')
    return {'status': job.status}


def _discover_items(job, connector):
    params = job.params or {}
    limit = max(1, min(500, int(params.get('limit') or 100)))
    items = []
    want_movies = job.content_type in {
        ProviderImportJob.ContentType.MOVIES,
        ProviderImportJob.ContentType.BOTH,
    }
    want_series = job.content_type in {
        ProviderImportJob.ContentType.SERIES,
        ProviderImportJob.ContentType.BOTH,
    }

    if want_movies:
        try:
            movies = list(connector.list_movies(page=1) or [])[:limit]
            for movie in movies:
                item = ProviderImportItem.objects.create(
                    job=job,
                    provider_item_id=str(movie.provider_item_id),
                    content_type=ProviderImportItem.ContentType.MOVIE,
                    title=movie.title or '',
                    original_title=movie.original_title or '',
                    year=movie.year,
                    tmdb_id=movie.tmdb_id,
                    imdb_id=movie.imdb_id or '',
                    raw_payload=sanitize_payload(movie.raw_payload or movie.to_dict()),
                    status=ProviderImportItem.Status.DISCOVERED,
                )
                items.append(item)
            append_log(job, 'info', f'Discovered {len(movies)} movie(s).')
        except ProviderContractUnknown as exc:
            append_log(job, 'warning', str(exc))
            if job.mode == ProviderImportJob.Mode.DISCOVER_ONLY and not want_series:
                raise

    if want_series:
        series_limit = limit if job.content_type == ProviderImportJob.ContentType.SERIES else max(
            1, limit - len(items),
        )
        try:
            series_list = list(connector.list_series(page=1) or [])[:series_limit]
            for series in series_list:
                item = ProviderImportItem.objects.create(
                    job=job,
                    provider_item_id=str(series.provider_item_id),
                    content_type=ProviderImportItem.ContentType.SERIES,
                    title=series.title or '',
                    original_title=series.original_title or '',
                    year=series.year,
                    tmdb_id=series.tmdb_id,
                    imdb_id=series.imdb_id or '',
                    raw_payload=sanitize_payload(series.raw_payload or series.to_dict()),
                    status=ProviderImportItem.Status.DISCOVERED,
                )
                items.append(item)
            append_log(job, 'info', f'Discovered {len(series_list)} series.')
        except ProviderContractUnknown as exc:
            append_log(job, 'warning', str(exc))
            if job.mode == ProviderImportJob.Mode.DISCOVER_ONLY and not items:
                raise

    job.total_items = len(items)
    job.save(update_fields=['total_items', 'updated_at'])
    if not items and job.mode == ProviderImportJob.Mode.DISCOVER_ONLY:
        raise ProviderContractUnknown(
            'No provider items discovered. Avasarami listing structure/API is not configured yet.'
        )
    return items


def _process_item(job, connector, item: ProviderImportItem):
    from .downloader import transfer_movie_candidate

    job.current_item_label = item.title or item.provider_item_id
    job.save(update_fields=['current_item_label', 'updated_at'])
    params = job.params or {}
    dry_run = bool(params.get('dry_run'))
    overwrite = bool(params.get('overwrite'))
    quality_preference = params.get('quality_preference') or []

    try:
        if item.content_type == ProviderImportItem.ContentType.MOVIE:
            movie, reason = match_movie(
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                title=item.title or item.original_title,
                year=item.year,
            )
            if movie:
                item.matched_movie = movie
                item.status = ProviderImportItem.Status.MATCHED
                item.status_message = f'Matched by {reason}'
                item.save()
                job.matched_items += 1
            else:
                item.status = ProviderImportItem.Status.SKIPPED
                item.status_message = 'No confident catalog match'
                item.save(update_fields=['status', 'status_message', 'updated_at'])
                job.skipped_items += 1
                job.processed_items += 1
                job.save(update_fields=[
                    'skipped_items', 'processed_items', 'matched_items', 'updated_at',
                ])
                return

            if job.mode == ProviderImportJob.Mode.DISCOVER_ONLY:
                job.processed_items += 1
                job.save(update_fields=['processed_items', 'matched_items', 'updated_at'])
                return

            if movie_has_available_archive(movie) and not overwrite:
                item.status = ProviderImportItem.Status.SKIPPED
                item.status_message = 'Archive already available'
                item.save(update_fields=['status', 'status_message', 'updated_at'])
                job.skipped_items += 1
                job.processed_items += 1
                job.save(update_fields=[
                    'skipped_items', 'processed_items', 'matched_items', 'updated_at',
                ])
                return

            candidates = list(connector.get_download_candidates(
                item.provider_item_id, 'movie',
            ) or [])
            candidate = _pick_candidate(candidates, quality_preference)
            if not candidate:
                item.status = ProviderImportItem.Status.SKIPPED
                item.status_message = 'No download candidate'
                item.save(update_fields=['status', 'status_message', 'updated_at'])
                job.skipped_items += 1
                job.processed_items += 1
                job.save(update_fields=[
                    'skipped_items', 'processed_items', 'matched_items', 'updated_at',
                ])
                return

            item.selected_candidate = candidate.public_dict()
            item.status = ProviderImportItem.Status.DOWNLOADING
            item.save(update_fields=['selected_candidate', 'status', 'updated_at'])

            if dry_run:
                item.status = ProviderImportItem.Status.SKIPPED
                item.status_message = 'Dry run — download skipped'
                item.save(update_fields=['status', 'status_message', 'updated_at'])
                job.skipped_items += 1
            else:
                result = transfer_movie_candidate(
                    connector=connector,
                    candidate=candidate,
                    movie=movie,
                    user=job.started_by,
                    overwrite=overwrite,
                    should_cancel=lambda: job_cancelled(job),
                    dry_run=False,
                )
                item.archive_asset = result.asset
                item.status = ProviderImportItem.Status.UPLOADED
                item.status_message = f'Uploaded {result.bytes_transferred} bytes'
                item.save()
                job.imported_files += 1

        elif item.content_type == ProviderImportItem.ContentType.SERIES:
            series, reason = match_series(
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                title=item.title or item.original_title,
                year=item.year,
            )
            if series:
                item.matched_series = series
                item.status = ProviderImportItem.Status.MATCHED
                item.status_message = f'Matched by {reason}'
                item.save()
                job.matched_items += 1
            else:
                item.status = ProviderImportItem.Status.SKIPPED
                item.status_message = 'No confident catalog match'
                item.save(update_fields=['status', 'status_message', 'updated_at'])
                job.skipped_items += 1

            if job.mode != ProviderImportJob.Mode.DISCOVER_ONLY:
                # Episode archive assets are not modeled yet; discover/match only.
                if item.status == ProviderImportItem.Status.MATCHED:
                    item.status = ProviderImportItem.Status.SKIPPED
                    item.status_message = (
                        'Series matched; episode archive transfer requires provider '
                        'download contract and episode archive model.'
                    )
                    item.save(update_fields=['status', 'status_message', 'updated_at'])
                    job.skipped_items += 1
        else:
            item.status = ProviderImportItem.Status.SKIPPED
            item.status_message = 'Unsupported item type for this job'
            item.save(update_fields=['status', 'status_message', 'updated_at'])
            job.skipped_items += 1

        job.processed_items += 1
        job.save(update_fields=[
            'processed_items', 'matched_items', 'imported_files',
            'skipped_items', 'failed_items', 'updated_at',
        ])
    except JobCancelled:
        raise
    except Exception as exc:
        item.status = ProviderImportItem.Status.FAILED
        item.status_message = str(exc)[:500]
        item.save(update_fields=['status', 'status_message', 'updated_at'])
        job.failed_items += 1
        job.processed_items += 1
        job.save(update_fields=[
            'failed_items', 'processed_items', 'updated_at',
        ])
        append_log(job, 'error', f'Item failed: {item.provider_item_id}', {
            'status_message': item.status_message,
        })


def _pick_candidate(candidates, quality_preference):
    if not candidates:
        return None
    prefs = [str(q).lower() for q in (quality_preference or [])]
    for pref in prefs:
        for candidate in candidates:
            if pref and pref in str(candidate.quality or '').lower():
                return candidate
    return candidates[0]
